import os
import sys
import subprocess
import tarfile
import time

# Configuration
PI_USER = "pi"
PI_HOST = "192.168.88.11"
REMOTE_DIR = "/home/pi/isp_core_build"
EXCLUDES = [
    "venv", ".venv", "node_modules", "__pycache__", ".git", ".env", "db.sqlite3", 
    "*.pyc", ".DS_Store", "deploy_core.py", "deploy_to_pi.bat", "start_dev.bat"
]

def create_tarball(output_filename="pkg.tar.gz"):
    print(f"[1/5] Creating archive {output_filename}...")
    with tarfile.open(output_filename, "w:gz") as tar:
        for item in os.listdir("."):
            if item in EXCLUDES or item.startswith("."):
                continue
            tar.add(item, filter=lambda x: None if any(exc in x.name for exc in EXCLUDES) else x)
    return output_filename

def run_command(cmd, shell=True):
    try:
        subprocess.run(cmd, shell=shell, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        sys.exit(1)

def deploy():
    tarball = create_tarball()
    
    print(f"[2/5] Cleaning remote directory {REMOTE_DIR}...")
    run_command(f"ssh {PI_USER}@{PI_HOST} \"rm -rf {REMOTE_DIR} && mkdir -p {REMOTE_DIR}\"")
    
    print(f"[3/5] Transferring archive to {PI_HOST}...")
    # Using scp (assuming it's in path)
    if os.name == 'nt': # Windows
        run_command(f"scp {tarball} {PI_USER}@{PI_HOST}:{REMOTE_DIR}/pkg.tar.gz")
    else:
        run_command(f"scp {tarball} {PI_USER}@{PI_HOST}:{REMOTE_DIR}/pkg.tar.gz")

    print("[3.5/5] Fixing DB Permissions...")
    # Grant CREATEDB and CREATEROLE to isp_user so it can create tenant DBs and Users
    run_command(f"ssh {PI_USER}@{PI_HOST} \"sudo -u postgres psql -c 'ALTER ROLE isp_user WITH CREATEDB CREATEROLE;'\"")
        
    print("[4/5] Building Docker Images on Pi (This may take a while)...")
    build_cmds = [
        f"cd {REMOTE_DIR}",
        "tar -xzf pkg.tar.gz",
        # Build Core
        "echo 'Building isp_core...'",
        "docker build -f backend/Dockerfile -t isp_core:latest .",
        # Build Manager
        "echo 'Building isp_manager...'",
        "docker build -f manager/Dockerfile -t isp_manager:latest manager/"
    ]
    
    remote_cmd = " && ".join(build_cmds)
    run_command(f"ssh {PI_USER}@{PI_HOST} \"{remote_cmd}\"")
    
    print("[5/5] Restarting Manager App...")
    manager_cmd = (
        "docker stop isp-manager 2>/dev/null || true && "
        "docker rm isp-manager 2>/dev/null || true && "
        "docker run -d --name isp-manager -p 8501:8501 --restart always "
        "-v /var/run/docker.sock:/var/run/docker.sock "
        "--network host " 
        "isp_manager:latest"
    )
    run_command(f"ssh {PI_USER}@{PI_HOST} \"{manager_cmd}\"")
    
    # Cleanup local
    os.remove(tarball)
    print("\n[SUCCESS] Deployment Complete!")
    print(f"Manager App: http://{PI_HOST}:8501")

if __name__ == "__main__":
    deploy()
