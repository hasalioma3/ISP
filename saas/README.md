# ISP Cloud: hosting the ISP billing app for other ISPs

`saas/` is a separate application that turns the ISP billing app (the rest of this repo) into a hosted service. The ISP app itself is not modified: every ISP gets its own unmodified copy of it, built from this repo.

```
saas/
  backend/     Django 4.2 + DRF + Celery: the master app (control plane)
  frontend/    React + Vite + Tailwind, Savanna design imported from ../frontend
  tenant/      docker-compose.tenant.yml: one ISP's instance
  docker-compose.yml       the master stack (+ shared Postgres/Redis for instances)
  build_tenant_images.sh   builds the images every instance runs
```

## What it does

| Area | How |
|---|---|
| **Sign-up & trial** | `/signup` creates the owner's account and queues provisioning. When the instance is up, a **free trial** (Settings → trial days, default 2) starts with every feature on. The owner signs in to their instance as `admin` with the password they chose. |
| **One instance per ISP** | Docker Compose project `saas-<slug>`: backend, Celery worker and beat, frontend, and the WhatsApp sidecar, from pre-built images. Each instance has its **own database** `t_<slug>` (and role) on the SaaS Postgres server, its own Redis index, its own port (9500+) and its own `/24` network. |
| **Lifecycle** | trial → active (owner subscribes) / suspended (trial over). active → past_due (invoice overdue) → suspended (after the grace days). Suspended = containers stopped, data kept. Admins can also resume, extend a trial, cancel, restart, re-apply config, and delete (only with a zero balance). |
| **Per-subscriber pricing** | Pricing plans are fully configurable: which service types count (PPPoE/hotspot/static), active-only or all accounts, peak/average/end-of-month count, **graduated or volume tiers**, base fee, included subscribers, minimum/maximum charge, first-month proration, per-plan collection/payout fees. A live calculator is in the editor and on the sign-up page. |
| **Counting** | Every hour the worker reads each instance's subscriber counts straight from its database (read-only) into a daily snapshot. Invoices are priced from those snapshots. |
| **Invoices** | Issued on the configured day of the month for the previous month, and **paid from the money held for the ISP** when it covers it. Otherwise the ISP pays by STK from its account page. |
| **Collections** | All customers of all ISPs pay to the **platform's** shortcode (see below). Every payment is in the master's ledger per ISP. |
| **Payouts** | B2B (BusinessPayBill/BusinessBuyGoods) to the ISP's paybill or till, or B2C to a phone, on a daily/weekly/manual schedule, with optional **two-person approval**, a reserve, a minimum and a fee. A failed payout is reversed into the balance automatically. |
| **ISP portal** (`/account`) | Setup progress, trial countdown, open-my-system link, counts, estimated bill, choose/switch plan, invoices (pay by M-Pesa), statement (CSV), payouts and "pay me now", payout details, and cancellation requests. |
| **Platform admin** (`/admin`) | Dashboard, ISPs (detail: plan, discount, payout details, statement, adjustments, invoices, payouts, activity log, instance controls and logs), customer payments (assign unmatched ones), invoices, payouts (approve), pricing, team (admins vs support), and settings. |

## How the money flows

```
 customer ──STK──▶ Safaricom ──callback──▶ master /api/mpesa/stk/<tenant token>/
                                              │ 1. record Collection (unverified)
                                              │ 2. confirm with Safaricom (STK query): a forged callback creates no money
                                              │ 3. credit the ISP's ledger
                                              └ 4. forward the untouched body ──▶ instance /api/payments/callback/ (activates the customer)

 customer ──paybill──▶ Safaricom ──▶ master /api/mpesa/c2b/<secret>/confirmation/   (one URL per shortcode, shared)
                                              │ route: "<PREFIX> account" → that ISP; else the ONE ISP that has that username;
                                              │        else "Not matched" for an admin to assign
                                              │ credit the ledger
                                              └ forward with the account number as the ISP knows it ──▶ instance C2B confirmation

 ledger balance − open invoices − reserve ──▶ payout (B2B/B2C) ──▶ result callback ──▶ succeeded / reversed
```

Why it's built this way:
- **Money is never read from an ISP's database.** An ISP's admin controls their instance. Only Safaricom's own callbacks to the master create money in the ledger.
- **Each ISP's STK callbacks carry a secret per-ISP token**, so the master knows whose payment it is. Each instance's `MPESA_CALLBACK_URL` points at the master.
- **The ISP app is unchanged.** It still tells customers to pay with their username as the account number. Routing by username covers that. The per-ISP prefix (e.g. `ACME john`) is for usernames that exist at two ISPs.
- **Two Daraja apps.** Instances get a separate Daraja app with only *M-Pesa Express*. Instances are the ISPs' own servers and their backups include the env. The platform app (C2B, STK query, B2B/B2C) never leaves the master.

## Running it

```bash
cd saas
cp .env.example .env                  # fill it in (SAAS_ENCRYPTION_KEY, passwords, admin email)
./build_tenant_images.sh              # images the instances run (re-run after changing the ISP app)
docker compose up -d --build
```

The master UI is at **https://<host>:9443/** (self-signed). Sign in with `SAAS_ADMIN_EMAIL` / `SAAS_ADMIN_PASSWORD`. The `api` container migrates and runs `bootstrap` on start (first admin + a starter "Standard" plan), and writes a self-signed certificate for the instances into the `saas_tenant_certs` volume.

Then, in **Settings**:
1. **Public address** (HTTPS, reachable by Safaricom), and **instances' host** (the IP or domain ISPs and their routers use).
2. **M-Pesa collection**: shortcode, passkey, the platform Daraja app, and the separate instance Daraja app. Click **Test**, then **Register with Safaricom** for the C2B URLs.
3. **Payouts**: initiator name and password, Safaricom's certificate (PEM; sandbox and production differ), schedule and approval.
4. **Pricing**: edit the Standard plan or add your own.

Without Docker (UI work, tests): `cd saas/backend && ../../backend/venv/bin/python manage.py test cloud`. `SAAS_ORCHESTRATOR=fake` (the default outside the compose stack) records instance actions instead of running them.

### Updating the ISP app for everyone

```bash
./saas/build_tenant_images.sh 2026-12-01      # a new tag
# set SAAS_IMAGE_TAG=2026-12-01 in saas/.env for new sign-ups, restart worker;
# existing ISPs: set their image tag and "Re-apply config" (each instance then needs `migrate`, see below)
```

Instance migrations run at provisioning. After an image upgrade, run `docker compose -p saas-<slug> -f saas/tenant/docker-compose.tenant.yml --env-file <env> exec backend python manage.py migrate` per ISP. Automating that rollout is the next step (see Not done yet).

## Not done yet (first draft)

- **Safaricom has not been called for real**: payouts (B2B/B2C), STK query, C2B registration and the platform STK push are covered by tests with mocked replies only. Try them on the Daraja sandbox first: shortcode 600000-series, the sandbox certificate, and a public HTTPS URL (e.g. a tunnel) for the callbacks.
- **Reaching ISPs' routers.** An instance talks to its MikroTiks over the RouterOS API, so each ISP needs a route from this server (VPN/WireGuard per ISP, or public IPs with an allow-list). Not automated yet.
- **Domains.** Instances are on `https://<host>:<port>/` with a shared self-signed certificate. Subdomains (`acme.cloud.example.com`) behind a reverse proxy with real certificates would be the production setup.
- **Image upgrades** for existing ISPs (rolling migrate), per-ISP backups to off-site storage from the master, and SMS to owners. Owners get email only now (configure SMTP in `.env`).
- **Capacity.** Each instance is ~5 containers and roughly 0.6-1 GB RAM. A Raspberry Pi holds only a few. Plan a bigger host or a VPS for real customers.
