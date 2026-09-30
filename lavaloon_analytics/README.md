# LavaLoon Analytics — Frappe App

**Version 0.1.0 · 28 September 2026**

A native Frappe/ERPNext app for multi‑brand social & content analytics: ingest LinkedIn (and other) exports **or** pull leads/conversions/revenue from **Frappe CRM**, set annual + monthly **targets**, and track pacing — all inside your bench, governed by Frappe roles and permissions.

> Status: Phase‑1 core. Built to Frappe conventions and **static‑validated** (all DocType JSON parses; all Python compiles). It has **not** been run on a live bench in this build environment — follow "Verify after install" below on your bench.

## For reviewers
Start with **`docs/CODE_REVIEW.md`** (component-by-component breakdown + a risk table) and **`CHANGELOG.md`**. The app is static-validated only — not yet run on a live bench; see "Verify after install".

## Requirements
Frappe Framework **v15** (works alongside ERPNext / Frappe CRM). Python ≥ 3.10.

## Install
```bash
cd ~/frappe-bench
bench get-app lavaloon_analytics /path/to/lavaloon_analytics   # or a git URL
bench --site yoursite.local install-app lavaloon_analytics
bench --site yoursite.local migrate
bench restart
```
Install creates the roles **Analytics Manager / Analyst / Viewer**, a default **Marketing Company** ("LavaLoon"), and the **LavaLoon Analytics Settings** single.

## Data model (DocTypes)
- **Marketing Company** — the brand/tenant (name, colours, logo). Isolate users with a **User Permission** on this DocType.
- **Marketing Metric** — one row per date × metric (`metric_name` is namespaced, e.g. `linkedin.impressions`, `overall.leads`), with `source` = Manual / Upload / Frappe CRM.
- **Marketing Target** — Annual + 12 Monthly per metric per year (`is_auto_suggested` when monthly = annual ÷ 12).
- **Marketing Demographic** — audience breakdowns (location / industry / seniority / …).
- **Marketing Upload** — attach an export; parsing runs automatically on insert.
- **LavaLoon Analytics Settings** (single) — Frappe CRM sync mapping.

## How to use
1. **Create brands & access** — add a *Marketing Company* per brand; give each user a role and a *User Permission* on their company so they only see their data.
2. **Get data in** — either:
   - **Upload**: *Marketing Upload* → attach a LinkedIn Content / Followers / Visitors export. It auto‑detects the template, writes daily *Marketing Metric* rows and audience demographics, and records the window.
   - **Manual**: add *Marketing Metric* rows (or call `add_manual_metrics`), e.g. for Facebook/TikTok or leads/revenue.
   - **Frappe CRM**: in *Settings*, tick **Enable Frappe CRM Sync**, set the company and the CRM field mapping. A daily job (and `run_crm_sync`) writes `overall.leads`, `overall.conversions`, `overall.revenue`.
3. **Set targets** — add *Marketing Target* rows, or call `save_targets(company, fiscal_year, annual, monthly)` — monthly auto‑fills to annual ÷ 12 and you can override any month.
4. **Read it** — open the **LavaLoon Analytics** workspace; run the **Marketing Pacing** report (pick company, year, metric) for monthly actual‑vs‑target with variance, % achieved and status.

## API (whitelisted)
`lavaloon_analytics.api.get_dashboard(company, from_date, to_date)` ·
`…api.add_manual_metrics(company, date, platform, values)` ·
`…api.save_targets(company, fiscal_year, annual, monthly)` ·
`…crm_sync.run_crm_sync(company)`

## Verify after install (smoke checklist)
1. `bench --site … install-app` completes; **LavaLoon Analytics** appears in the workspace switcher.
2. The three Analytics roles exist; assign one to a test user + a User Permission on a Marketing Company; confirm they see only that company's metrics.
3. Create a *Marketing Upload* with a LinkedIn export → status becomes **Parsed**, Marketing Metric rows appear for the window.
4. Add a few *Marketing Target* rows → **Marketing Pacing** report shows actual‑vs‑target.
5. (If CRM present) enable sync in Settings, run `bench --site … execute lavaloon_analytics.crm_sync.run_crm_sync` → `overall.*` metrics appear.

## Frappe CRM mapping notes
Defaults assume `CRM Lead` and `CRM Deal`. Adjust the DocType/status/revenue field names in *Settings* to match your Frappe CRM (leads counted by creation month; conversions = deals at the "Won" status; revenue = sum of the revenue field on won deals).

## Phase 2 (not in this build)
- The rich tabbed dashboard UI (Overall + per‑channel tabs, audience charts) from the standalone web app — as a bundled Frappe **Page** or by embedding the existing React app.
- Competitor‑benchmark DocType + ingest; Frappe **Insights** dashboards; scheduled report emails.
