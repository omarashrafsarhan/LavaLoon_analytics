## [0.2.0] — 2026-10-11

Addresses the v0.1 review (design flaw + three gaps). Built to Frappe conventions and
**static-validated** (all DocType/report JSON parses; all Python compiles); not yet run on a bench.

### Fixed — target distribution (design flaw: monthly = annual ÷ 12)
- New `metrics.py` classifies every metric as **flow / rate / score** and derives monthly targets by a chosen **distribution**: `even` (annual ÷ 12, for yearly-total flows), `ramp` (baseline → annual over 12 months, for scores and run-rate flows), `flat` (the annual level every month, for rates), or `manual`.
- `Marketing Target` gains `metric_kind`, `distribution`, `baseline_value`; `save_targets(...)` now takes optional `distribution` and `baselines` maps and computes each month accordingly (SEO scores ramp, engagement/AI-mention rates stay flat, impressions/followers ramp from a baseline, leads split evenly). Manual per-month overrides still win.

### Added — weekly view (gap)
- `api.get_trend(company, metric, granularity=daily|weekly|monthly, from, to)` — kind-aware aggregation (sum for flows, average for rates/scores).
- New **Marketing Weekly** script report (week-of, value, WoW change, WoW %).

### Added — competitor data model (gap)
- New DocTypes **Marketing Competitor** (name, platform, page URL, **mapped product/service**, **selection rationale**, source, active) and **Marketing Competitor Snapshot** (period + new followers / posts / comments / reactions).
- Competitor export now ingests into snapshots (and auto-creates competitor records); new **Marketing Competitor Benchmark** report ranks the latest snapshot per competitor. The product-mapping + rationale fields also answer the CEO's competitor requests (#2, #3).

### Added — GA4 / Search Console feed (gap)
- Ingest templates for **GA4** CSV (Date + Sessions/Active users → `website.visitors`) and **Google Search Console** CSV (Date + Clicks + Impressions → `seogeo.searchClicks` / `seogeo.searchImpressions`), with CSV column-based auto-detection.
- New metric sources **GA4** and **Search Console**; Settings gains `ga4_property_id` and `search_console_site` placeholders for a future API feed.

### Changed
- Workspace adds a **Competitors** card and the Weekly / Competitor-Benchmark reports.
- `get_dashboard` aggregation is now kind-aware via `metrics.aggregate`.

### Review carefully (see docs/CODE_REVIEW.md)
- GA4/SC column names vary by export locale/version — the templates match common English headers; verify against a real export.
- Competitor snapshot period comes from the first row's dates (LinkedIn competitor export format); confirm for other sources.
- Still no live GA4/SC **API** feed (CSV upload only) and no automated tests — both tracked.

# Changelog

All notable changes to **LavaLoon Analytics (Frappe app)**. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project uses SemVer.

> ⚠️ This release was built to Frappe conventions and **static-validated only**
> (every DocType JSON parses; all Python compiles). It has **not** been run on a
> live Frappe bench yet — see `docs/CODE_REVIEW.md` and README "Verify after install".

## [0.1.0] — 2026-09-28

### Added — data model (DocTypes)
- **Marketing Company** — the brand/tenant record (name, slug, colours, logo). Basis of multi-brand isolation.
- **Marketing Metric** — one row per `date × metric_name` (namespaced, e.g. `linkedin.impressions`), with `platform` and `source` (Manual / Upload / Frappe CRM).
- **Marketing Target** — Annual + 12 Monthly rows per metric/year; `is_auto_suggested` flags months auto-filled as annual ÷ 12.
- **Marketing Demographic** — audience breakdowns (location / industry / seniority / jobFunction / companySize) with `as_of` snapshot date.
- **Marketing Upload** — attach an export; parsing runs automatically on insert; stores status, template, row count and window.
- **LavaLoon Analytics Settings** (Single) — Frappe CRM sync toggle + field mapping.

### Added — logic
- **`hooks.py`** — wires `Marketing Upload.after_insert → ingest.parse_upload`, a `daily` scheduler for CRM sync, and `after_install`.
- **`install.py`** — creates the 3 roles, a default **LavaLoon** brand, and seeds Settings defaults.
- **`ingest.py`** — canonical LinkedIn template library (Content / Followers / Visitors) + `.xlsx`/`.csv` parser → daily metrics + demographics, with auto template detection.
- **`crm_sync.py`** — daily + on-demand sync from Frappe CRM: leads/month (`overall.leads`), won deals (`overall.conversions`), won revenue (`overall.revenue`).
- **`api.py`** — whitelisted `add_manual_metrics`, `save_targets` (annual → auto monthly), `get_dashboard`.
- **Report: Marketing Pacing** (Script Report) — monthly actual vs target, variance, % achieved, status.
- **Workspace: LavaLoon Analytics** — links to the DocTypes and the pacing report.
- **Roles** — Analytics Manager / Analyst / Viewer, applied in every DocType's permissions.

### Fixed (hardening applied during self-review — see docs/CODE_REVIEW.md)
- `Marketing Upload` status writes used `doc.db_set({...})` (a dict where a fieldname is expected) → now `frappe.db.set_value(doctype, name, {...})`. **Would not have persisted the fields.**
- CRM sync `last_sync` used `set_value(single, None, …)` → now `set_single_value(...)` (correct API for a Single DocType).
- Legacy **`.xls`** now raises a clear, actionable error instead of an opaque openpyxl failure.
- Removed dead code (`srccol`, `_month_key`).

### Security
- Added a tenancy guard `_guard(company)` to **all** whitelisted API methods — `get_dashboard` previously used `frappe.get_all` with no permission check (**cross-brand read risk**); it now enforces read permission on the Marketing Company (respects roles + User Permission).
- `run_crm_sync` restricted to **System Manager / Analytics Manager**.

### Known limitations / review carefully (tracked in docs/CODE_REVIEW.md)
- 🔴 **`.xls` ingest**: LinkedIn exports are often legacy `.xls`; only `.xlsx`/`.csv` are read. Needs conversion (LibreOffice / pandas+xlrd) or a documented `.xlsx` requirement.
- 🔴 **No DB unique constraint** behind the read-then-write upserts (metrics/targets) → duplicates possible under concurrency. Recommend a composite unique index.
- 🟠 **CRM sync** aggregates full history every run and overwrites `overall.*` months (can clobber manual entries; heavy on large CRMs). Recommend a trailing window + source-aware merge.
- 🟠 **CRM field mapping** defaults may not match your Frappe CRM — verify in Settings.
- 🟠 **Workspace/Report JSON** not validated on a live bench.
- 🟡 `get_dashboard` aggregates in Python; `row_count` counts metric cells; `overall.revenue` has no currency handling.

[0.1.0]: initial release
