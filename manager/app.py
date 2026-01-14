import streamlit as st
import subprocess
import os
import secrets
import string
import time
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configuration
BASE_PORT = int(os.environ.get("BASE_PORT", 8001))
HOST_IP = os.environ.get("HOST_IP", "localhost") 
# DOCKER_GATEWAY: Used by spawned containers to reach DB/Redis on the host (or shared container network)
# On Windows Docker Desktop, use 'host.docker.internal'
# On Linux (Pi), default bridge/host networking might use '172.17.0.1' or the host IP if bound to 0.0.0.0
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "host.docker.internal")

st.set_page_config(page_title="ISP Tenant Manager", layout="wide")

st.title(f"ISP Billing - Tenant Manager ({HOST_IP})")

def get_db_connection():
    # Connect to the Postgres Server that holds the tenant DBs
    # In this architecture, Manager App runs in a container, so we use DOCKER_GATEWAY or a specific DB container hostname
    db_host = os.environ.get("DB_HOST", DOCKER_GATEWAY)
    
    conn = psycopg2.connect(
        host=db_host, 
        database="postgres",
        user=os.environ.get("DB_USER", "isp_user"),
        password=os.environ.get("DB_PASSWORD", "isp_password")
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    return conn

def create_tenant_db(company_name):
    # Sanitize name
    safe_name = "".join(c for c in company_name if c.isalnum()).lower()
    db_name = f"isp_{safe_name}"
    user_name = f"user_{safe_name}"
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Create User
        cur.execute(sql.SQL("CREATE USER {} WITH PASSWORD %s").format(sql.Identifier(user_name)), [password])
    except psycopg2.errors.DuplicateObject:
        # User exists, update password so we know it for the new container
        cur.execute(sql.SQL("ALTER USER {} WITH PASSWORD %s").format(sql.Identifier(user_name)), [password])

    # Grant the new user to the creator (isp_user) so we can assign ownership
    cur.execute(sql.SQL("GRANT {} TO isp_user").format(sql.Identifier(user_name)))
        
    try:
        # Create Database
        cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db_name), sql.Identifier(user_name)))
    except psycopg2.errors.DuplicateDatabase:
        pass # Database exists, proceed.
    
    cur.close()
    conn.close()
    
    return db_name, user_name, password, None

def deploy_container(company_name, port, db_name, db_user, db_pass):
    safe_name = "".join(c for c in company_name if c.isalnum()).lower()
    container_name = f"isp-{safe_name}"
    
    # Docker Run Command
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:8000",
        "--restart", "always",
        # Connect to the shared network 'isp_network' so we can access isp-db and isp-redis by name
        "--network", "isp_network",
        "-e", f"DATABASE_URL=postgresql://{db_user}:{db_pass}@isp-db:5432/{db_name}",
        "-e", f"CELERY_BROKER_URL=redis://isp-redis:6379/1",
        "-e", f"CELERY_RESULT_BACKEND=redis://isp-redis:6379/1",
        "-e", f"SERVER_IP={HOST_IP}",
        "-e", f"ALLOWED_HOSTS={HOST_IP},localhost,127.0.0.1",
        "-e", f"CSRF_TRUSTED_ORIGINS=http://{HOST_IP}:{port}",
        "isp_core:latest"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def create_superuser(container_name, username, email, password):
    # Use DJANGO_SUPERUSER_* env vars with createsuperuser --noinput to avoid interactive prompt
    cmd = [
        "docker", "exec",
        "-e", f"DJANGO_SUPERUSER_USERNAME={username}",
        "-e", f"DJANGO_SUPERUSER_EMAIL={email}",
        "-e", f"DJANGO_SUPERUSER_PASSWORD={password}",
        container_name,
        "python", "manage.py", "createsuperuser", "--noinput"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True, "Superuser created successfully"
    except subprocess.CalledProcessError as e:
        return False, e.stderr

# UI
with st.form("deploy_form"):
    st.subheader("New Tenant Details")
    company_name = st.text_input("Company Name")
    
    st.subheader("Admin User Defaults")
    admin_user = st.text_input("Admin Username", value="admin")
    admin_email = st.text_input("Admin Email", value="admin@example.com")
    admin_pass = st.text_input("Admin Password", type="password", value="admin123")
    
    submit = st.form_submit_button("Deploy New Customer")
    
if submit and company_name:
    st.info(f"Deploying for {company_name}...")
    
    # 1. Database
    db_name, db_user, db_pass, error = create_tenant_db(company_name)
    if error:
        st.error(f"Database Error: {error}")
    else:
        st.success(f"Database {db_name} created!")
        
        # 2. Port Allocation (Naive)
        # In production, check used ports.
        # For valid demo, we hash the name to a port or increment. 
        # Using timestamp for now to avoid collision in simple test
        port = 8000 + (hash(company_name) % 1000) 
        if port < 8000: port += 1000
        
        # 3. Deploy
        success, msg = deploy_container(company_name, port, db_name, db_user, db_pass)
        
        if success:
            st.success(f"Deployed successfully on Port {port}!")
            st.code(f"URL: http://{HOST_IP}:{port}\nDB: {db_name}\nUser: {db_user}\nPass: {db_pass}")
            
            # 4. Create Superuser
            st.info("Creating Superuser...")
            container_name = f"isp-{''.join(c for c in company_name if c.isalnum()).lower()}"
            # Give container a moment to start
            time.sleep(5) 
            
            su_success, su_msg = create_superuser(container_name, admin_user, admin_email, admin_pass)
            if su_success:
                st.success(f"Superuser '{admin_user}' created!")
            else:
                st.error(f"Superuser Creation Failed: {su_msg}")
                
        else:
            st.error(f"Docker Error: {msg}")

st.header("Active Tenants")
# Check running containers
try:
    res = subprocess.run(["docker", "ps", "--format", "table {{.Names}}\t{{.Ports}}\t{{.Status}}"], capture_output=True, text=True)
    st.text(res.stdout)
except Exception:
    st.error("Could not list containers")
