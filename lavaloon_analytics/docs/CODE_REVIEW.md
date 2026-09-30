# Code Review Guide — LavaLoon Analytics (Frappe app)

**Version 0.1.0 · 28 September 2026**

This guide breaks the app down component by component so a reviewer can move quickly.
Each section says **what the file does**, walks its **blocks/functions**, and marks
**⚠️ review-carefully** points. A consolidated risk table is at the top.

> Status: static-validated only (JSON parses, Python compiles). **Not yet run on a
> live bench.** Runtime verification steps are in the README ("Verify after install").

## Suggested review order
1. `docs/CODE_REVIEW.md` (this file) → the risk table below.
2. Data model — the six DocType JSONs (shape + permissions + tenancy).
3. `ingest.py` (most logic + highest risk).
4. `crm_sync.py` (external data + scheduler).
5. `api.py` (whitelisted surface + tenancy guard).
6. `report/marketing_pacing`, `workspace`, `install.py`, `hooks.py`.

## Severity legend
🔴 High — verify/fix before production · 🟠 Medium — plan a follow-up · 🟡 Low — nice to have.

## Review-carefully summary

| # | Sev | File / block | Why it matters | Recommended action |
|---|-----|--------------|----------------|--------------------|
| R1 | 🔴 | `ingest.py::_load_sheets` | Only `.xlsx`/`.csv` are parsed; LinkedIn exports are frequently legacy `.xls` (now raises a clear error, but ingest of real files fails). | Add server-side conversion (LibreOffice `soffice` or `pandas`+`xlrd`), or document/require `.xlsx`. |
| R2 | 🔴 | `ingest._upsert_metric`, `api.save_targets`, `crm_sync._agg_by_month` | Upserts are read-then-write with **no DB unique constraint** → duplicates under concurrency / double-trigger. | Add composite unique index: Metric `(company,date,metric_name)`; Target `(company,period_type,fiscal_year,month,metric_name)` via a patch. |
| R3 | 🟠 | `crm_sync._agg_by_month` | Aggregates **all** CRM history each run and overwrites `overall.*` for every month → heavy on large CRMs; **clobbers manual** `overall.*`. | Limit to a trailing window (e.g. 13 months); skip/merge months whose existing metric `source = Manual`. |
| R4 | 🟠 | `ingest.py`, `crm_sync.py`, `install.py` (`ignore_permissions=True`) | Background writes bypass permission checks; tenancy then relies on the `company` value being trustworthy. | OK for jobs, but confirm `Marketing Upload.company` is User-Permission-enforced at creation; document the assumption. |
| R5 | 🟠 | `api._guard` | New tenancy guard uses `frappe.has_permission(doc=company)`. | Verify on-bench that it enforces **User Permissions** for non-managers as intended. |
| R6 | 🟠 | `crm_sync.py` + Settings | Default field mapping (`CRM Lead`/`CRM Deal`/`status=Won`/`deal_value`) may not match the target CRM. | Confirm DocType/field names against the actual Frappe CRM; adjust in Settings. |
| R7 | 🟡 | `api.get_dashboard` | Aggregates in Python after a (now date-filtered) query. | Fine at current scale; push aggregation to SQL for large data. |
| R8 | 🟡 | `ingest.parse_upload` | `row_count` counts **metric cells**, not sheet rows (field label says "Rows Ingested"). | Rename label or count rows. |
| R9 | 🟠 | `workspace/…json`, `report/…json` | Workspace JSON schema is finicky; not migrate-tested here. | Confirm both load on `bench migrate`. |
| R10 | 🟡 | `crm_sync` `overall.revenue` | Sums the raw revenue field; no currency normalization. | Decide currency handling / company currency. |
| R11 | 🟡 | DocType permissions | `Viewer` has export/report/share flags. | Decide whether Viewer should export/share. |

## Fixed during this self-review
- `doc.db_set({...})` (dict as fieldname — would not persist) → `frappe.db.set_value(...)`. *(`ingest.py`)*
- `set_value(single, None, …)` → `set_single_value(...)`. *(`crm_sync.py`)*
- Added `_guard(company)` to every whitelisted API — closes a **cross-brand read** hole in `get_dashboard`. *(`api.py`)*
- `run_crm_sync` restricted to System Manager / Analytics Manager. *(`crm_sync.py`)*
- Clear error for legacy `.xls`; removed dead code. *(`ingest.py`, `crm_sync.py`)*

---

## A. `hooks.py` — app wiring
Declares metadata and three integration points:
- `doc_events = {"Marketing Upload": {"after_insert": "…ingest.parse_upload"}}` → parsing runs automatically when an upload is created.
- `scheduler_events = {"daily": ["…crm_sync.scheduled_sync"]}` → CRM sync runs daily.
- `after_install = "…install.after_install"` → seeds roles/brand/settings.
⚠️ R4: after_insert runs in the request; the scheduler runs as Administrator. Keep that in mind for permission context.

## B. Data model (DocType JSON) & tenancy
All data DocTypes carry a `company` **Link → Marketing Company** and share the same
`permissions` block (System Manager + Analytics Manager/Analyst/Viewer).
**Tenancy model:** isolation is achieved by giving each user a **User Permission** on
their Marketing Company; Frappe then auto-filters any DocType with a `company` link.
Key fields:
- **Marketing Metric**: `company, date, platform (Select), metric_name (Data, namespaced), value (Float), source (Select)`. `in_standard_filter` set for fast filtering.
- **Marketing Target**: `company, period_type (Annual/Monthly), fiscal_year (Int), month (Int), metric_name, target_value, is_auto_suggested (Check)`.
- **Marketing Upload**: `company, upload_file (Attach), status/template/row_count/min_date/max_date/error_log (read-only, set by ingest)`.
- **Marketing Demographic**: `company, platform, scope, dimension, label, value, as_of`.
- **LavaLoon Analytics Settings** (`issingle:1`): CRM mapping fields.
⚠️ R2: no composite unique index on the natural keys. ⚠️ R11: confirm Viewer flags.

## C. `install.py` — `after_install()`
Creates the three roles if missing, a default **LavaLoon** Marketing Company, and seeds
Settings defaults. Uses `ignore_permissions=True` (fine during install). ⚠️ R4.

## D. `ingest.py` — spreadsheet → metrics (highest-risk file)
- **`TEMPLATES`** — declarative map of the three LinkedIn exports: which `sheet`, which
  `match_cols` identify it, `date_col`, and `fields` (source column → namespaced metric),
  plus optional `scale` (engagement rate ×100) and `demographics` sheets.
- **Helpers** — `_num` (strips `, %` → float), `_to_date` (Excel/string → date),
  `_load_sheets` (openpyxl for `.xlsx`, `csv` for `.csv`; ⚠️ **R1** raises on `.xls`),
  `_find_sheet`/`_header_row`/`_col` (fuzzy, case-insensitive matching in the first 8 rows).
- **`detect(sheets)`** — picks the template whose sheet is present **and** whose
  `match_cols` all appear. Returns `None` if nothing matches (upload → `Failed`).
- **`parse_upload(doc, method)`** — the orchestrator:
  1. loads the attached File, `detect()`s the template;
  2. finds the header row + column indexes;
  3. iterates rows → `_upsert_metric(company, date, platform, metric, value, "Upload")`, tracking min/max date;
  4. rebuilds demographics for each dimension (delete-then-insert scoped by company/platform/scope/dimension);
  5. writes status/template/row_count/window via `frappe.db.set_value` (fixed from `db_set(dict)`).
  Wrapped in `try/except` → on error the upload is marked `Failed` with the traceback tail.
  ⚠️ R1 (.xls), ⚠️ R2 (dup upserts), ⚠️ R4 (ignore_permissions on insert), ⚠️ R8 (`count` semantics).
- **`_upsert_metric(...)`** — `get_value` by `(company,date,metric_name)`; update if found else insert. ⚠️ R2.

```python
def _upsert_metric(company, d, platform, metric_name, value, source):
    name = frappe.db.get_value("Marketing Metric",
        {"company": company, "date": d, "metric_name": metric_name}, "name")   # ⚠️ R2 no unique index
    if name:
        frappe.db.set_value("Marketing Metric", name, {"value": value, "source": source, "platform": platform})
    else:
        frappe.get_doc({...}).insert(ignore_permissions=True)                    # ⚠️ R4
```

## E. `crm_sync.py` — Frappe CRM → metrics
- **`scheduled_sync()`** — daily entry; runs only if `crm_sync_enabled` and a `sync_company` is set.
- **`run_crm_sync(company=None)`** — whitelisted, **role-restricted** (`frappe.only_for`).
- **`sync_company_crm(company)`** — guards that the Lead DocType exists, then aggregates:
  leads → `overall.leads`; won deals → `overall.conversions`; won revenue → `overall.revenue`;
  stamps `last_sync` via `set_single_value`.
- **`_agg_by_month(...)`** — `frappe.get_all` the source rows, bucket by month-start, then
  upsert one metric per month. ⚠️ **R3** (full-history rewrite + clobbers manual), ⚠️ R6 (mapping), ⚠️ R10 (currency).

```python
rows = frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=0)  # ⚠️ R3 no date window
...
buckets[key] += float(r.get(sum_field) or 0) if sum_field else 1.0
```

## F. `api.py` — whitelisted surface
- **`_guard(company)`** — `frappe.has_permission("Marketing Company", doc=company, throw=True)`; called first in every method (**tenancy**). ⚠️ R5 verify on-bench.
- **`add_manual_metrics(company, date, platform, values)`** — upserts Manual metrics. Uses `.insert()` (respects create permission).
- **`save_targets(company, fiscal_year, annual, monthly)`** — writes Annual + 12 Monthly targets; monthly auto = annual ÷ 12 unless an override is supplied (then `is_auto_suggested=0`). ⚠️ R2.
- **`get_dashboard(company, from_date, to_date)`** — now date-filtered in SQL + guarded; aggregates per metric (mean for `RATE` metrics, else sum). ⚠️ R7 (Python aggregation).

## G. `report/marketing_pacing/marketing_pacing.py`
Script Report `execute(filters)` → for each month: `sum(value)` actual vs the monthly
`Marketing Target`, with variance, % achieved, and Ahead/On track/Behind status.
Uses a **parameterized** SQL query (safe). ⚠️ Performance on very large tables (per-month queries).

## H. `workspace/lavaloon_analytics/…json`
A public Workspace with card breaks + links to the DocTypes and the pacing report.
⚠️ **R9**: confirm it loads on `bench migrate` (Workspace JSON is schema-sensitive).

---

## Testing guidance (on a bench)
See README "Verify after install". Minimum: install-app + migrate succeed; roles created;
a User Permission scopes a test user to one brand; an `.xlsx` upload reaches status **Parsed**
with metrics; targets + the **Marketing Pacing** report render; (if CRM present) `run_crm_sync`
writes `overall.*`. Add unit tests under `lavaloon_analytics/tests/` for `detect()`,
`_upsert_metric()` idempotency, and `save_targets()` auto-fill before production.
