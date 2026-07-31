# Deploy Runbook: Mac (dev) → Pi 5 (production)

Workflow: debug and test on this Mac (`https://192.168.88.254`), and once you're
confident it's right, push to the Pi (`https://192.168.88.253`).

## Two deploy scripts — which one to use

- **`./deploy_update.sh`** — the 95% case. Routine code changes, bug fixes,
  new migrations, `.env`/`.env.prod` edits. Fast: reuses Docker's build
  cache, and only recreates containers whose image actually changed.
- **`./deploy_fresh.sh`** — a genuinely new system from scratch, or a hard
  reset if the Pi's Docker state is somehow broken/needs to be nuked. Slow
  by design: it wipes the build cache (`docker system prune -af`) and
  rebuilds everything unconditionally, every time.

Don't reach for `deploy_fresh.sh` out of habit — the cache wipe is the whole
reason it's slow, and routine changes don't need it.

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
   curl -sk -o /dev/null -w "%{http_code}\n" https://192.168.88.253/
   ```
   Expect `200`. Spot-check the admin portal and a subscriber lookup.

That's it for almost every change — new features, bug fixes, new migrations,
and `.env`/`.env.prod` edits are all picked up automatically: rsync copies the
env files (they aren't excluded), and a rebuild re-bakes both the Vite build
args and the container runtime env, so there's no separate step for env
changes.

## Occasional Pi maintenance

`deploy_update.sh` never prunes anything, so old image layers accumulate on
the Pi's disk over many updates. Every so often (not every deploy), free up
space with:
```bash
ssh pi@192.168.88.253 "docker image prune -f"
```
That only removes untagged/dangling images — never anything a running
container is actually using, so it's safe to run anytime, unlike
`deploy_fresh.sh`'s `system prune -af`.

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
