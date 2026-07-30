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
   This rsyncs the repo to the Pi, backs up the Pi's database to
   `~/isp_backups/pre_deploy_<timestamp>.sql`, stops the stack, prunes unused
   images/build cache (never volumes), rebuilds everything, and runs
   migrations.

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
