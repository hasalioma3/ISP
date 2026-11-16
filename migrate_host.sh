#!/bin/bash
# Move the whole system (database, media, WhatsApp login, backups, env,
# certs, code) from the current host to a new one with as little downtime
# as possible. Run from this Mac, in the repo root:
#
#   ./migrate_host.sh prepare  <new_host> <new_user>   # safe, repeatable, no downtime
#   ./migrate_host.sh cutover  <new_host> <new_user>   # the short downtime window
#   ./migrate_host.sh finish   <new_host> <new_user>   # after DNS/port-forward points at the new host
#   ./migrate_host.sh rollback <new_host> <new_user>   # go back to the old host
#
# The old host defaults to production (OLD_HOST/OLD_USER below); override
# with OLD_HOST=... OLD_USER=... ./migrate_host.sh ...
#
# How downtime is kept short:
#   prepare  copies the code/env/certs exactly as they are on the old host,
#            builds the images on the new host and loads a full "warm" copy
#            of the database and volumes -- all while the old host keeps
#            serving customers. It times the database copy, which is what
#            the real downtime will be. It also runs `migration_check` on
#            the new host: can it reach every router, M-Pesa, Google?
#            The new host's Celery and WhatsApp are NOT started, so nothing
#            runs twice (reminders, usage polling, the WhatsApp session).
#   cutover  stops the old app (writes stop), copies the database once more
#            plus the WhatsApp login and media, starts everything on the new
#            host, then turns the old host into a TCP forwarder (ports 80,
#            443, 8000 -> new host). Anything still pointing at the old IP --
#            DNS caches, M-Pesa callbacks, routers' portal redirect -- keeps
#            working while you switch DNS / port forwarding at your own pace.
#   finish   removes the forwarder. The old host's volumes are left as they
#            are (a fallback) until you delete them yourself.
#
# Other companies (tenants) on the same host are not moved by this script.
set -euo pipefail

CMD="${1:-}"
NEW_HOST="${2:-}"
NEW_USER="${3:-}"
OLD_HOST="${OLD_HOST:-192.168.58.252}"
OLD_USER="${OLD_USER:-pi}"
REMOTE_DIR="ISP"
VOLUMES="isp_media_volume isp_static_volume isp_whatsapp_session isp_backup_volume"
FORWARDER=isp_migration_forwarder

if [[ -z "$CMD" || -z "$NEW_HOST" || -z "$NEW_USER" ]]; then
    sed -n '2,13p' "$0"
    exit 1
fi
if [[ "$NEW_HOST" == "$OLD_HOST" ]]; then
    echo "❌ The new host is the same as the old one ($OLD_HOST)."; exit 1
fi

# One SSH connection per host, reused by every command below.
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$HOME/.ssh/cm-isp-%r@%h:%p" -o ControlPersist=15m -o ServerAliveInterval=20)
old() { ssh "${SSH_OPTS[@]}" "$OLD_USER@$OLD_HOST" "cd ~/$REMOTE_DIR && $*"; }
new() { ssh "${SSH_OPTS[@]}" "$NEW_USER@$NEW_HOST" "cd ~/$REMOTE_DIR && $*"; }
new_raw() { ssh "${SSH_OPTS[@]}" "$NEW_USER@$NEW_HOST" "$*"; }
step() { echo; echo "▶ $*"; }

# Values from the old host's env (ports may be customised).
env_val() { old "grep -E '^$1=' .env.prod | tail -1 | cut -d= -f2-" 2>/dev/null || true; }

uses_sqlite() { old "grep -qE '^DATABASE_URL=sqlite' .env.prod"; }

wait_for_db() {  # $1 = old|new
    for _ in $(seq 1 60); do
        if $1 "docker compose exec -T db sh -c 'pg_isready -h localhost -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "❌ Postgres on $1 host did not come up"; exit 1
}

copy_db() {  # copy_db <from> <to>   (old|new)
    local from=$1 to=$2 start end
    start=$(date +%s)
    if uses_sqlite; then
        # SQLite: the file itself (the app on the source side is stopped at
        # cutover, so it's consistent; at prepare it's a best-effort copy).
        $from "cat backend/db.sqlite3" | $to "cat > backend/db.sqlite3"
    else
        # Custom-format dump streamed straight into pg_restore: nothing is
        # written to disk on either host, and it's the fastest option.
        $from "docker compose exec -T db sh -c 'pg_dump -Fc -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\"'" \
            | $to "docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --role=\"\$POSTGRES_USER\" -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" 2>/tmp/pg_restore.log; grep -i error /tmp/pg_restore.log | grep -v \"does not exist\" | head -20; true'"
        if [[ ${PIPESTATUS[0]} -ne 0 ]]; then echo "❌ pg_dump on the $from host failed"; exit 1; fi
    fi
    end=$(date +%s)
    DB_SECONDS=$((end - start))
    echo "   database copied in ${DB_SECONDS}s"
}

copy_volume() {  # copy_volume <name> <from> <to>
    # Through a throwaway postgres:15-alpine container -- an image both hosts
    # already have, so nothing is pulled from the internet mid-migration.
    $2 "docker run --rm -v $1:/v:ro --entrypoint tar postgres:15-alpine -C /v -cz ." \
        | $3 "docker volume create $1 >/dev/null && docker run --rm -i -v $1:/v --entrypoint sh postgres:15-alpine -c 'rm -rf /v/* /v/.[!.]* 2>/dev/null; tar -C /v -xz'"
}

preflight() {
    step "Checking SSH to both hosts"
    old "true" || { echo "❌ Cannot SSH to old host $OLD_USER@$OLD_HOST"; exit 1; }
    new_raw "true" || { echo "❌ Cannot SSH to new host $NEW_USER@$NEW_HOST (set up key login first: ssh-copy-id $NEW_USER@$NEW_HOST)"; exit 1; }
    old "docker compose ps -q db | grep -q ." || { echo "❌ The app isn't running on the old host"; exit 1; }
    if ! new_raw "command -v docker >/dev/null"; then
        echo "🐳 Installing Docker on the new host..."
        new_raw "curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker \$USER"
        echo "✅ Docker installed. Run this command again (the next login picks up the docker group)."
        exit 0
    fi
    new_raw "docker info >/dev/null" || { echo "❌ Docker on the new host isn't usable by $NEW_USER"; exit 1; }
    local free
    free=$(new_raw "df -Pk ~ | awk 'NR==2{print \$4}'")
    echo "   new host free space: $((free / 1024 / 1024)) GB"
}

prepare() {
    preflight
    step "Copying code, env files and certificates from the old host (exact same version)"
    new_raw "mkdir -p ~/$REMOTE_DIR"
    old "tar -cz --exclude=node_modules --exclude=__pycache__ --exclude=backend/logs/*.log --exclude=.git ." \
        | new "tar -xz"
    new "mkdir -p backend/logs"
    # So the new host can be tested by its own IP before DNS moves.
    new "grep -q '^ALLOWED_HOSTS=.*$NEW_HOST' .env.prod || sed -i 's/^ALLOWED_HOSTS=\\(.*\\)/ALLOWED_HOSTS=\\1,$NEW_HOST/' .env.prod"
    new "grep -q '^CSRF_TRUSTED_ORIGINS=.*$NEW_HOST' .env.prod || sed -i 's|^CSRF_TRUSTED_ORIGINS=\\(.*\\)|CSRF_TRUSTED_ORIGINS=\\1,https://$NEW_HOST|' .env.prod"

    step "Creating volumes and building images on the new host (the old host keeps serving)"
    new "for v in isp_postgres_data $VOLUMES; do docker volume create \$v >/dev/null; done"
    new "docker compose build"

    step "Starting the database on the new host"
    new "docker compose up -d db redis"
    wait_for_db new

    step "Warm copy of the database (timed -- this is roughly the downtime at cutover)"
    copy_db old new

    step "Copying media, WhatsApp login, backups"
    for v in $VOLUMES; do echo "   $v"; copy_volume "$v" old new; done

    step "Starting the web app on the new host (no Celery, no WhatsApp yet) and migrating"
    new "docker compose up -d --no-deps backend frontend"
    sleep 5
    new "docker compose exec -T backend python manage.py migrate --noinput"

    step "Checking what the new host can reach"
    new "docker compose exec -T backend python manage.py migration_check" || {
        echo "⚠️  Fix the ❌ items above before cutting over (re-run prepare afterwards; it's safe)."
    }

    new "echo $(date +%s) > .migration_prepared"
    echo
    echo "✅ New host prepared. Test it now: https://$NEW_HOST (sign in, open Subscribers, Network)."
    echo "   Changes you make there are thrown away at cutover -- the real data is copied again."
    echo "   Expected downtime at cutover: about $((DB_SECONDS + 40))s."
    echo "   When ready: ./migrate_host.sh cutover $NEW_HOST $NEW_USER"
}

cutover() {
    new "test -f .migration_prepared" || { echo "❌ Run prepare first"; exit 1; }
    preflight
    local http https backend
    http=$(env_val ISP_HTTP_PORT); http=${http:-80}
    https=$(env_val ISP_HTTPS_PORT); https=${https:-443}
    backend=$(env_val ISP_BACKEND_PORT); backend=${backend:-8000}
    echo
    read -r -p "Cut over now? Customers can't pay or log in for ~1 minute. [y/N] " ok
    [[ "$ok" == "y" || "$ok" == "Y" ]] || exit 1
    local t0; t0=$(date +%s)

    step "Stopping the app on the old host (downtime starts)"
    old "docker compose stop celery_beat celery_worker whatsapp_service backend"
    new "docker compose stop backend celery_worker celery_beat whatsapp_service 2>/dev/null || true"

    step "Final database copy"
    copy_db old new

    step "Final copy of the WhatsApp login and media"
    copy_volume isp_whatsapp_session old new
    copy_volume isp_media_volume old new

    step "Starting everything on the new host"
    new "docker compose up -d"
    sleep 5
    new "docker compose exec -T backend python manage.py migrate --noinput"
    local code
    code=$(new "curl -sk -o /dev/null -w '%{http_code}' https://localhost:$https/api/settings/site/" || echo 000)
    if [[ "$code" != "200" ]]; then
        echo "❌ New host health check returned $code. Rolling back to the old host..."
        rollback_quiet
        exit 1
    fi

    step "Turning the old host into a forwarder (old IP -> new host)"
    old "docker compose stop frontend"
    local image
    image=$(old "docker inspect --format '{{.Config.Image}}' \$(docker compose ps -aq frontend)")
    old "cat > .forwarder.conf <<EOF
events {}
stream {
    server { listen 80;  proxy_pass $NEW_HOST:$http; }
    server { listen 443; proxy_pass $NEW_HOST:$https; }
    server { listen 8000; proxy_pass $NEW_HOST:$backend; }
}
EOF
docker rm -f $FORWARDER >/dev/null 2>&1 || true
docker run -d --name $FORWARDER --restart unless-stopped -p $http:80 -p $https:443 -p $backend:8000 \
    -v \$PWD/.forwarder.conf:/fw.conf:ro --entrypoint sh $image -c \
    'M=/usr/lib/nginx/modules/ngx_stream_module.so; : > /tmp/n.conf; [ -f \$M ] && echo \"load_module \$M;\" > /tmp/n.conf; cat /fw.conf >> /tmp/n.conf; exec nginx -c /tmp/n.conf -g \"daemon off;\"'" >/dev/null
    sleep 2
    if old "docker ps --filter name=$FORWARDER --filter status=running -q | grep -q ."; then
        echo "   forwarder running on the old host"
    else
        echo "⚠️  The forwarder didn't start (see: ssh $OLD_USER@$OLD_HOST docker logs $FORWARDER)."
        echo "   The new host is live; just point DNS / port forwarding at $NEW_HOST now."
    fi
    local t1; t1=$(date +%s)
    new "rm -f .migration_prepared"

    echo
    echo "✅ Cut over in $((t1 - t0))s. The new host ($NEW_HOST) is live."
    echo "Next:"
    echo "  1. Point the domain / router port-forward / tunnel at $NEW_HOST."
    echo "  2. If routers only allow API access from the old IP, add $NEW_HOST (Network -> router -> WAN management)."
    echo "  3. Set PI_HOST=$NEW_HOST in deploy_update.sh (and update_from_github if used there)."
    echo "  4. Check Settings -> Notifications: WhatsApp should show Connected (session was copied)."
    echo "  5. Then: ./migrate_host.sh finish $NEW_HOST $NEW_USER"
    echo "  Problem? ./migrate_host.sh rollback $NEW_HOST $NEW_USER"
}

rollback_quiet() {
    old "docker rm -f $FORWARDER >/dev/null 2>&1 || true"
    new "docker compose stop" || true
    old "docker compose up -d"
}

rollback() {
    preflight
    echo "Rolling back makes the OLD host live again."
    read -r -p "Copy the data written on the new host since cutover back to the old host first? [Y/n] " back
    old "docker rm -f $FORWARDER >/dev/null 2>&1 || true"
    new "docker compose stop backend celery_worker celery_beat whatsapp_service"
    if [[ "$back" != "n" && "$back" != "N" ]]; then
        old "docker compose up -d db"
        wait_for_db old
        old "docker compose stop backend celery_worker celery_beat 2>/dev/null || true"
        copy_db new old
        copy_volume isp_whatsapp_session new old
        copy_volume isp_media_volume new old
    fi
    new "docker compose stop"
    old "docker compose up -d"
    old "docker compose exec -T backend python manage.py migrate --noinput"
    echo "✅ Old host ($OLD_HOST) is live again; the new host is stopped."
}

finish() {
    old "docker rm -f $FORWARDER >/dev/null 2>&1 || true; rm -f .forwarder.conf"
    old "docker compose stop"
    echo "✅ Forwarder removed and the old stack stopped. Its volumes are kept as a fallback;"
    echo "   delete them on $OLD_HOST when you're sure (docker volume ls | grep isp_)."
}

case "$CMD" in
    prepare) prepare ;;
    cutover) cutover ;;
    rollback) rollback ;;
    finish) finish ;;
    *) sed -n '2,13p' "$0"; exit 1 ;;
esac
