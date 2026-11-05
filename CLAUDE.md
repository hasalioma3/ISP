# CLAUDE.md

ISP billing and network-automation system for a Kenyan ISP. Customers pay through M-Pesa (STK Push or C2B paybill/till), and the system turns their service on or off on MikroTik routers (PPPoE, Hotspot, Static IP). It also handles vouchers, FUP and data caps, and SMS/WhatsApp/Telegram notifications. (TR-069/GenieACS CPE management was removed in 2026-11 to keep the Pi light; it's in git history if needed.)

## Layout

- `backend/` is the Django 4.2 + DRF project. The settings package is `isp_billing/` (settings, `celery.py`, urls). Apps live in `apps/`.
- `frontend/` is React 18 + Vite + TypeScript + Tailwind, with Radix UI, TanStack Query, Zustand and axios. The `@` alias points to `src/`.
- `nginx/default.conf` is baked into the frontend image. It serves the SPA and proxies `/api/`, `/django-admin/`, `/static/` and `/media/` to the backend.
- `whatsapp-service/` is a Node Baileys sidecar. It is internal only and reached at `http://whatsapp_service:3000`. It is send-only (history sync, presence and link previews are off) and reconnects with exponential backoff; it's built with `npm ci`, so change Baileys by updating `package-lock.json`.
- Root shell scripts handle deploy and tenant provisioning (see below). `debug_mt.py`, `teststk2.py`, `add_walled_garden.py`, `backend/test_mk.py` and `backend/test_mpesa.py` are ad-hoc scripts, not a test suite.

## Backend apps (`backend/apps/`)

| App | Mounted at | Purpose |
|---|---|---|
| `customers` | `/api/customers/` | `Customer` is the custom `AUTH_USER_MODEL` (subscribers and staff in one table). Staff `role` is admin, technician or sales; gate endpoints with `RoleAllowed(...)` from `customers/permissions.py`, and remember superusers always pass. |
| `billing` | `/api/billing/` | `BillingPlan` (service_type `pppoe`/`hotspot`/`static`), `Subscription`, `Transaction`, `UsageRecord`, `VoucherBatch`/`Voucher`. Purchase and switch logic is in `billing/services.py` (`purchase_plan`, `apply_subscription`, `purchase_plan_from_balance`). |
| `payments` | `/api/payments/` | `PaymentRequest` (STK), `PaymentCallback`, `C2BPayment`. The code is in `services/mpesa_service.py` (Daraja API) and `services/payment_processor.py` (callback to credit to activate). C2B URLs carry `MPESA_C2B_SECRET` in the path (`_check_c2b_token`). Management command: `register_c2b_urls`. |
| `network` | `/api/network/` | `Router`, `PPPoESecret`, `HotspotUser`, `ActiveSession`. `services/mikrotik_service.py` is the low-level RouterOS API wrapper (`routeros-api`). `services/network_automation.py` holds the `network_automation` singleton, which covers activate/suspend, FUP, profile/user sync, router provisioning, the hotspot login page and WAN management access. Static-IP usage is read from each customer's simple-queue counters, with the baseline kept in `StaticQueueCounter` (not `ActiveSession`). |
| `notifications` | `/api/notifications/` | SMS (Africa's Talking), WhatsApp (sidecar or AT), Telegram. Credentials are stored **encrypted in the DB** (`NotificationSettings`, using `NOTIFICATIONS_ENCRYPTION_KEY`), not in env. |
| `analytics`, `accounting`, `inventory`, `sitesettings` | `/api/<name>/` (sitesettings is at `/api/settings/`) | Dashboards/reports, expenses, stock, and branding/site config. |

### How the pieces connect

- **Signals do the network work.** Saving a `Subscription` (`customers/signals.py`) calls `network_automation.activate_customer` or suspends the customer, and keeps `Customer.status` in sync. Saving a `BillingPlan` or changing its routers (`billing/signals.py`) queues `sync_plan_to_routers` on commit. Tests must patch these (for example `apps.billing.signals.sync_plan_to_routers.delay` and `...network_automation.activate_customer`) or they will try to reach a router.
- **The payment flow:** STK Push creates a `PaymentRequest`. The M-Pesa callback goes to `PaymentProcessor.process_callback`, which creates a `Transaction` and calls `purchase_plan`. That creates the `Subscription`, whose signal activates the customer on MikroTik, and then a confirmation SMS is sent.
- **Celery beat** (`isp_billing/celery.py`, using `DatabaseScheduler`) runs these tasks:
  - expiry checks, every minute
  - data-limit and FUP enforcement, every minute
  - usage polling, every `USAGE_POLL_SECONDS` (default 15s)
  - pending-payment cleanup, every 30 minutes
  - expiry reminders, daily at 08:00

  A `beat_init` hook forces the usage-poll interval into the DB row.
- **MikroTik provisioning conventions** are set in `settings.py`:
  - ether1 is the WAN.
  - ether2 and ether5 are reserved and never touched.
  - ether3, ether4 and wlan1 (if it exists) are bridged into `hotspot_bridge`.
  - The "default" profiles are throttled to `1M/1M`.
- REST defaults: JWT auth (SimpleJWT, Bearer), `IsAuthenticated` unless the view overrides it, `PageNumberPagination` with 20 per page. `TIME_ZONE` is `Africa/Nairobi`.

## Commands

The main way to run the app locally is Docker, served at `https://192.168.88.254`:
```bash
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py test                 # all tests
docker compose exec backend python manage.py test apps.network.tests.FupEnforcementTests
```
- `./deploy_local.sh [--with-workers]` starts a sandbox stack from `.env.local`. It refuses to run unless `MPESA_ENVIRONMENT=sandbox`. Workers are opt-in because their tasks contact real routers.
- To work without Docker: `cd backend && venv/bin/python manage.py runserver` (and `... test`). Without `DATABASE_URL` the DB falls back to SQLite.
- Frontend: `cd frontend && npm run dev` (port 80; proxies `/api` to `127.0.0.1:8000`), `npm run build` (`tsc && vite build`), `npm run lint`.
- `makemigrations` per app, for example `venv/bin/python3 manage.py makemigrations billing`.

**Migrations do not run in the container entrypoint.** This is on purpose: backend, celery_worker and celery_beat share one image and would race each other. They run once, from the deploy scripts. Always run migrations explicitly after `up`.

## Deploy and multi-tenancy

See `DEPLOY.md`. Code is developed on the Mac and deployed to a Raspberry Pi 5 production host (user `pi`, `~/ISP`; the IP is `PI_HOST` in the scripts).
- `./deploy_update.sh` covers the normal case. It rsyncs, backs up the DB to `~/isp_backups/`, builds with the cache, runs `up -d`, then migrates.
- `./deploy_fresh.sh` is only for a new host or a broken Docker state.
- `./provision_company.sh <slug> "<Name>" <port>` and `./deprovision_company.sh` manage extra tenants. Each tenant runs its own app containers from `docker-compose.company.yml` with `companies/<slug>.env`. All tenants share one Postgres and one Redis (one DB, and one Redis index, per tenant) over the external `isp_shared_network`.
- Compose volumes are `external: true`. They must exist before `up`, and the deploy scripts create them.
- Env files: `.env.prod` (the default `ISP_ENV_FILE`), `.env.local`, and `companies/*.env`. All of these are gitignored; only `.env.local.example` and `companies/.env.template` are tracked. Never commit secrets.

## Conventions and gotchas

- Code comments in this repo are long and explain *why*. Match that style when you change non-obvious behavior.
- `backend/apps/network/tests.py` is indented with tabs. Keep the indentation of whichever file you are editing.
- Never publish a port for `whatsapp_service`. Network isolation is its only access control.
- Removing an entry from `beat_schedule` doesn't remove it from `DatabaseScheduler`'s table; delete the `PeriodicTask` row in a data migration too (see `network/migrations/0009_remove_cpe_sync_schedule.py`).
- Changes that touch the real network (Pi, VPS, MikroTik) should be prepared as commands for the user to run, not run directly.
- `backend/logs/isp_billing.log` is tracked and changes constantly. Don't commit its churn.
