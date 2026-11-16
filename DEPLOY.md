# Deploy Runbook: Mac (dev) → Pi 5 (production)

Workflow: debug and test on this Mac (`https://192.168.88.254`), and once you're
confident it's right, push to the Pi (`https://192.168.88.252`).

## Two deploy scripts — which one to use

- **`./deploy_update.sh`** — the 95% case. Routine code changes, bug fixes,
  new migrations, `.env`/`.env.prod` edits. Fast: reuses Docker's build
  cache, and only recreates containers whose image actually changed.
- **`./deploy_fresh.sh`** — a genuinely new system from scratch, or a hard
   reset if the Pi's Docker state is somehow broken. It rebuilds and
   recreates the main project, but preserves existing Docker images and
   build cache, including images used by other projects.

Don't reach for `deploy_fresh.sh` out of habit — routine changes don't need
the full rebuild.

## Normal deploy (the 95% case: code changes, migrations, env tweaks)

1. **Develop & test locally on the Mac:**
   ```bash
   docker compose up -d --build
   ```
   Confirm it in a browser at `https://192.168.88.254`, and if you changed
   models, make sure `docker compose exec backend python manage.py migrate`
   runs clean locally first.

2. **Commit and push:**
   ```bash
   git add -A
   git commit -m "..."
   git push origin Phase-2
   ```

3. **Deploy to the Pi:**
   ```bash
   ./deploy_update.sh
   ```
   Rsyncs the repo to the Pi, then on the Pi: backs up the database to
   `~/isp_backups/pre_update_<timestamp>.sql`, runs `docker compose build`
   (fast — cached layers are reused, only what changed rebuilds) and
   `docker compose up -d` (no `--force-recreate` — Compose only restarts a
   container if its image/config actually changed, so unrelated services
   stay up), then runs migrations. Refuses to run (tells you to use
   `deploy_fresh.sh` instead) if Docker isn't installed yet or nothing's
   running on the Pi at all.

4. **Verify:**
   ```bash
   curl -sk -o /dev/null -w "%{http_code}\n" https://192.168.88.252/
   ```
   Expect `200`. Spot-check the admin portal and a subscriber lookup.

That's it for almost every change — new features, bug fixes, new migrations,
and `.env`/`.env.prod` edits are all picked up automatically: rsync copies the
env files (they aren't excluded), and a rebuild re-bakes both the Vite build
args and the container runtime env, so there's no separate step for env
changes.

## Updating from GitHub (alternative to deploy_update.sh)

Instead of pushing from the Mac, the Pi can pull from GitHub itself:

```bash
cd ~/ISP && ./update_from_github.sh          # deploys origin/main
cd ~/ISP && ./update_from_github.sh Phase-2  # or another branch
```

It fetches the branch, makes `~/ISP` match it exactly, then runs
`update_on_pi.sh`: DB backup, cached rebuild, `up -d`, then migrate. Only
pushed commits are deployed, and env files stay on the Pi, so edit `.env.prod`
there directly. The script refuses to run while the server stores its data in
SQLite, because `backend/db.sqlite3` is tracked in git and would be overwritten.

One-time setup on the Pi:

1. **Deploy key** (read-only access to the private repo):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/isp_deploy -N "" -C "pi-deploy"
   printf 'Host github.com\n  IdentityFile ~/.ssh/isp_deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
   cat ~/.ssh/isp_deploy.pub
   ```
   In GitHub, open the repo's **Settings → Deploy keys → Add deploy key**,
   paste the key, and leave **Allow write access** off. Then check it with
   `ssh -T git@github.com`; it should greet you with the repo name.
2. **Turn `~/ISP` into a clone** (keeps `.env.prod` and other ignored files):
   ```bash
   cd ~/ISP
   git init -b main
   git remote add origin git@github.com:hasalioma3/ISP.git
   git fetch origin
   ```
   The first `./update_from_github.sh` then replaces the rsynced files with
   the GitHub version.

## Occasional Pi maintenance

Neither deploy script prunes images. Old image layers can accumulate on the
server over time. To remove dangling images/build cache, inspect first and
prune manually when you are certain they are not needed:
```bash
ssh pi@192.168.88.252 "docker image prune"
```
Review Docker's prompt before confirming; pruning may remove untagged images.

## Rollback

If a deploy goes bad:

```bash
ssh pi@192.168.88.252 "cd ~/ISP && \
    docker compose exec -T db psql -U isp_user -d isp_billing_prod < ~/isp_backups/pre_deploy_<timestamp>.sql"
```

The backup was taken with `--clean --if-exists`, so this drops and recreates
objects cleanly — no manual schema wrangling needed. For a code rollback too,
`git checkout <previous-commit>` on the Mac, then run `./deploy_fresh.sh`
again.

## One-time-only setup (already done — reference only)

These steps were for the initial Pi migration and shouldn't be repeated on a
normal deploy: creating the external Docker volumes
(`isp_postgres_data`/`isp_static_volume`/`isp_media_volume`), and restoring
the very first DB dump + media tarball from the Mac. `deploy_fresh.sh` assumes
those volumes already exist and already have data — running it against a
brand-new, empty Pi would start the stack with an empty database, not restore
anything.

## Known limitation

`deploy_fresh.sh` always does a full rebuild of every service
(`--build --force-recreate`), even for a one-line frontend change. Existing
images and build cache are retained; replaced image tags may leave old
untagged layers on disk.

## Multi-company (Phase 2)

The Pi can host more than one company's portal at once, each fully isolated:
its own Postgres database, its own Redis DB index (so Celery queues never
cross between companies), its own backend/frontend/celery containers, and
its own port. Postgres and Redis themselves are shared processes — a
separate Postgres/Redis container per company isn't worth the RAM on a Pi 5
when a separate database already gives full data isolation.

**Provision a new company:**
```bash
./provision_company.sh <slug> "<Display Name>" <port>
# e.g. ./provision_company.sh acme "Acme Wireless" 8081
```
Creates the database + role, writes `companies/<slug>.env`, builds and starts
that company's containers, runs migrations, creates a default `admin`
account (password printed once — save it), and seeds the company name into
their branding settings. **`MPESA_*` and `MIKROTIK_*` in the generated env
file are placeholders** — edit them with that company's real credentials and
router, then `docker compose -f docker-compose.company.yml --env-file companies/<slug>.env -p isp-<slug> up -d --force-recreate`
before they can take real payments or reach a router.

`companies/*.env` files hold real secrets and are gitignored — they exist
only on the Pi, not in the repo.

**Remove a company:**
```bash
./deprovision_company.sh <slug>
```
Destructive — stops its containers, drops its database, deletes its env
file. Asks you to re-type the slug to confirm.

**Redeploying code changes** (`./deploy_fresh.sh`) only rebuilds the main
`isp-billing` project (`docker-compose.yml`) — it does not touch company
stacks. To ship a code change to a company too, rerun the same `docker
compose -f docker-compose.company.yml --env-file companies/<slug>.env -p
isp-<slug> up -d --build` command for each one (not yet wired into
`deploy_fresh.sh`).

## Monitoring (Netdata)

`docker-compose.monitoring.yml` runs a single Netdata container that watches
every container on the Pi (main project + all companies) via the Docker
socket, plus host CPU/RAM/disk/network. Standalone from the app stacks —
start it once on the Pi and leave it running:

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

Dashboard: `http://192.168.88.252:19999/`. It's on host networking (Netdata's
own recommendation, for accurate numbers), so there's no port mapping to
manage. `restart: unless-stopped` + Docker starting on boot means it survives
reboots on its own. No login by default — see the note at the top of the
compose file if that matters on your LAN.

## Backups and moving to a new host

Everything is in **Settings → Backups** (superadmins only).

**What a backup holds:** the database (`pg_dump`), every MikroTik's config (settings read over the API, plus a full
`/export` `.rsc` and binary `.backup` fetched over the router's FTP), uploaded files, and, only when an encryption
passphrase is set, the server's env (`SECRET_KEY`, `NOTIFICATIONS_ENCRYPTION_KEY`, M-Pesa keys) and the WhatsApp
login. Without `NOTIFICATIONS_ENCRYPTION_KEY`, the stored SMS/SMTP/router credentials restore blank, so set a
passphrase and keep it somewhere safe.

Archives are kept in the `isp_backup_volume` Docker volume (`/backups` in the backend and worker containers) and,
copied off-site to Google Drive and/or a Synology NAS (WebDAV, see below). Scheduled backups run hourly from beat
(`scheduled-backup`) and only start at the configured hour/day. From the shell:
`docker compose exec backend python manage.py backup_now`.

**Synology NAS** (Settings → Backups → Synology NAS), two ways in:

- *QuickConnect* (default; no port forwarding or VPN): enable QuickConnect on the NAS with DSM allowed under
  Advanced → Permission settings, and enter its ID. The app asks Synology's directory where the NAS is, tries its
  direct addresses first, and falls back to Synology's relay (speed-limited, so large archives take longer). It
  uses the File Station API, so the NAS account needs the File Station application and **must not have 2-step
  verification** (an unattended login can't answer it); use a dedicated account.
- *Direct address (WebDAV)*: install the *WebDAV Server* package with HTTPS (5006); the Pi needs a route to the
  NAS (LAN, VPN, or DDNS with 5006 forwarded).

Either way, create a shared folder and a dedicated user with Read/Write on it only, then "Test & save". Uploads go
to `<name>.part` and are renamed when complete, then size-checked. The app deletes copies beyond "Keep on the NAS",
so it needs delete rights; turn on the shared folder's Recycle Bin and Snapshot Replication so a compromised server
can't wipe the NAS copies too. To restore from the NAS, download the archive in File Station and use
`restore_backup` as below.

**Move to a new host with ~1 minute of downtime** (from this Mac):

```bash
ssh-copy-id USER@NEW_HOST
./migrate_host.sh prepare  NEW_HOST USER   # copy + build + warm DB copy + router reachability check; no downtime
./migrate_host.sh cutover  NEW_HOST USER   # stop old app, final DB/WhatsApp/media copy, start new, old forwards 80/443/8000
#   ...point DNS / port-forward / tunnel at NEW_HOST, update PI_HOST in deploy_update.sh...
./migrate_host.sh finish   NEW_HOST USER   # remove the forwarder, stop the old stack (its volumes are kept)
./migrate_host.sh rollback NEW_HOST USER   # if needed: make the old host live again (optionally copying new data back)
```

The old host defaults to production; override it with `OLD_HOST=... OLD_USER=...`. Other tenants (`companies/*`)
are not moved by the script.

**Restore when the old host is gone:**

```bash
./deploy_fresh.sh                                   # on the new host (set PI_HOST first); restore .env.prod from
                                                    # the backup's secrets/env if you no longer have it
docker compose stop celery_worker celery_beat
docker compose cp isp-backup-XXXX.tar.gz.enc backend:/backups/
docker compose exec backend python manage.py restore_backup /backups/isp-backup-XXXX.tar.gz.enc --passphrase '...'
docker compose exec backend python manage.py migrate
docker compose up -d
```

`restore_backup` restores the database and media, and extracts router configs, env and the WhatsApp login next to
the archive so you can apply them by hand. Delete that folder afterwards, because it holds passwords.
