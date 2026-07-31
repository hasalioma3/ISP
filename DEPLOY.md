# Deploy Runbook: Mac (dev) → Pi 5 (production)

Workflow: debug and test on this Mac (`https://192.168.88.254`), and once you're
confident it's right, push to the Pi (`https://192.168.88.253`).

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
   ./deploy_fresh.sh
   ```
   This rsyncs the repo to the Pi, then on the Pi: installs Docker if it
   isn't there yet (and if so, stops there — SSH group membership needs a
   fresh connection, so just re-run the script once it prints that message),
   backs up the database to `~/isp_backups/pre_deploy_<timestamp>.sql`, stops
   the stack, prunes unused images/build cache (never volumes), rebuilds
   everything, and runs migrations.

4. **Verify:**
   ```bash
   curl -sk -o /dev/null -w "%{http_code}\n" https://192.168.88.253/
   ```
   Expect `200`. Spot-check the admin portal and a subscriber lookup.

That's it for almost every change — new features, bug fixes, new migrations,
and `.env`/`.env.prod` edits are all picked up automatically: rsync copies the
env files (they aren't excluded), and `--build --force-recreate` re-bakes both
the Vite build args and the container runtime env, so there's no separate step
for env changes.

## Rollback

If a deploy goes bad:

```bash
ssh pi@192.168.88.253 "cd ~/ISP && \
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
(`--build --force-recreate`), even for a one-line frontend change. That's
deliberately simple and safe rather than fast — on a Pi 5 a full rebuild is a
couple of minutes, which is fine for how often you'll actually deploy.

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

Dashboard: `http://192.168.88.253:19999/`. It's on host networking (Netdata's
own recommendation, for accurate numbers), so there's no port mapping to
manage. `restart: unless-stopped` + Docker starting on boot means it survives
reboots on its own. No login by default — see the note at the top of the
compose file if that matters on your LAN.
