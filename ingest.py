import frappe, io, datetime, re

# ---- Template library -------------------------------------------------------
# Daily-flow templates: date column + value columns -> namespaced metrics.
# Competitor template: special period/leaderboard parse -> Marketing Competitor Snapshot.
# csv=True templates match on COLUMNS only (sheet-name agnostic) for CSV exports.
TEMPLATES = [
    {"key": "linkedin_content", "platform": "LinkedIn", "sheet": "Metrics",
     "match_cols": ["impressions", "reactions"], "date_col": "date",
     "fields": {"impressions (total)": "linkedin.impressions", "reactions (total)": "linkedin.likes",
                "comments (total)": "linkedin.comments", "reposts (total)": "linkedin.reposts",
                "clicks (total)": "linkedin.clicks", "engagement rate (total)": "linkedin.engagementRate"},
     "scale": {"linkedin.engagementRate": 100.0}},
    {"key": "linkedin_followers", "platform": "LinkedIn", "sheet": "New followers",
     "match_cols": ["total followers"], "date_col": "date",
     "fields": {"total followers": "linkedin.newFollowers"},
     "demographics": {"scope": "Followers", "sheets": {"Location": "location", "Job function": "jobFunction",
                      "Seniority": "seniority", "Industry": "industry", "Company size": "companySize"}}},
    {"key": "linkedin_visitors", "platform": "LinkedIn", "sheet": "Visitor metrics",
     "match_cols": ["total page views"], "date_col": "date",
     "fields": {"total page views (total)": "linkedin.pageViews", "total unique visitors (total)": "linkedin.uniqueVisitors"},
     "demographics": {"scope": "Visitors", "sheets": {"Location": "location", "Job function": "jobFunction",
                      "Seniority": "seniority", "Industry": "industry", "Company size": "companySize"}}},
    # GA4 (CSV export: Date + Sessions / Users)
    {"key": "ga4_traffic", "platform": "Website", "sheet": "Sheet1", "csv": True,
     "match_cols": ["date", "sessions"], "date_col": "date",
     "fields": {"sessions": "website.visitors"}},
    {"key": "ga4_traffic_users", "platform": "Website", "sheet": "Sheet1", "csv": True,
     "match_cols": ["date", "active users"], "date_col": "date",
     "fields": {"active users": "website.visitors"}},
    # Google Search Console (CSV export: Date + Clicks + Impressions)
    {"key": "search_console", "platform": "SEO", "sheet": "Sheet1", "csv": True,
     "match_cols": ["date", "clicks", "impressions"], "date_col": "date",
     "fields": {"clicks": "seogeo.searchClicks", "impressions": "seogeo.searchImpressions"}},
    # LinkedIn competitor benchmark (leaderboard over a period)
    {"key": "linkedin_competitor", "platform": "LinkedIn", "kind": "competitor",
     "sheet": "COMPETITORS", "match_cols": ["page", "new follower"]},
]

def _num(x):
    if x is None or x == "":
        return 0.0
    try:
        return float(re.sub(r"[,\s%]", "", str(x)))
    except Exception:
        return 0.0

def _to_date(x):
    if isinstance(x, (datetime.datetime, datetime.date)):
        return x if isinstance(x, datetime.date) else x.date()
    for f in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(str(x).strip(), f).date()
        except Exception:
            pass
    try:
        return frappe.utils.getdate(x)
    except Exception:
        return None

def _load_sheets(filename, content):
    name = (filename or "").lower()
    if name.endswith(".csv"):
        import csv
        rows = list(csv.reader(io.StringIO(content.decode("utf-8", "ignore"))))
        return {"Sheet1": rows}
    if name.endswith(".xls"):
        raise ValueError("Legacy .xls files aren't supported. Re-save the export as .xlsx and upload again.")
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}

def _find_sheet(sheets, name):
    for k in sheets:
        if str(k).lower() == name.lower() or name.lower() in str(k).lower():
            return sheets[k]
    return None

def _header_row(rows, keys):
    for i in range(min(15, len(rows))):
        low = [str(c).lower() for c in rows[i]]
        if all(any(k in c for c in low) for k in keys):
            return i
    return 0

def _col(header, name):
    for j, c in enumerate(header):
        if name.lower() in str(c).lower():
            return j
    return None

def _sheet_cols(rows):
    cols = set()
    for i in range(min(15, len(rows))):
        for c in rows[i]:
            cols.add(str(c).lower())
    return cols

def _resolve_sheet(sheets, tpl):
    """For csv/column-matched templates, pick the sheet that actually contains the match columns."""
    if not tpl.get("csv"):
        return _find_sheet(sheets, tpl["sheet"])
    for rows in sheets.values():
        cols = _sheet_cols(rows)
        if all(any(mc in c for c in cols) for mc in tpl["match_cols"]):
            return rows
    return None

def detect(sheets):
    names = [str(s).lower() for s in sheets]
    allcols = set()
    for rows in sheets.values():
        allcols |= _sheet_cols(rows)
    for t in TEMPLATES:
        cols_ok = all(any(mc in c for c in allcols) for mc in t["match_cols"])
        if not cols_ok:
            continue
        if t.get("csv") or t.get("kind") == "competitor":
            # sheet-name agnostic (csv) OR competitor sheet present
            if t.get("kind") == "competitor" and not any(t["sheet"].lower() in n or "competitor" in n for n in names):
                # competitor: also accept if the page/new-follower columns exist anywhere
                pass
            return t
        if any(t["sheet"].lower() in n for n in names):
            return t
    return None

def parse_upload(doc, method=None):
    try:
        fdoc = frappe.get_doc("File", {"file_url": doc.upload_file})
        content = fdoc.get_content()
        if isinstance(content, str):
            content = content.encode("utf-8", "ignore")
        sheets = _load_sheets(doc.upload_file, content)
        tpl = detect(sheets)
        if not tpl:
            frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed",
                "error_log": "Could not match a known template (LinkedIn Content/Followers/Visitors/Competitor, GA4, Search Console)."})
            return
        if tpl.get("kind") == "competitor":
            return _parse_competitor(doc, sheets, tpl)
        _parse_daily(doc, sheets, tpl)
    except Exception:
        frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed", "error_log": frappe.get_traceback()[-1400:]})
        frappe.db.commit()

def _parse_daily(doc, sheets, tpl):
    rows = _resolve_sheet(sheets, tpl)
    if not rows:
        frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed",
            "error_log": "Expected sheet/columns for '%s' not found." % tpl["key"]}); return
    hr = _header_row(rows, tpl["match_cols"]); header = rows[hr]
    dcol = _col(header, tpl["date_col"])
    colmap = {mn: _col(header, src) for src, mn in tpl["fields"].items()}
    src_label = {"ga4_traffic": "GA4", "ga4_traffic_users": "GA4", "search_console": "Search Console"}.get(tpl["key"], "Upload")
    count = 0; mn_d = None; mx_d = None
    for i in range(hr + 1, len(rows)):
        d = _to_date(rows[i][dcol]) if dcol is not None else None
        if not d:
            continue
        mn_d = d if not mn_d or d < mn_d else mn_d
        mx_d = d if not mx_d or d > mx_d else mx_d
        for mn, j in colmap.items():
            if j is None:
                continue
            val = _num(rows[i][j]) * tpl.get("scale", {}).get(mn, 1.0)
            _upsert_metric(doc.company, d, tpl["platform"], mn, val, src_label)
            count += 1
    if tpl.get("demographics") and mx_d:
        for sh, dim in tpl["demographics"]["sheets"].items():
            s = _find_sheet(sheets, sh)
            if not s:
                continue
            frappe.db.delete("Marketing Demographic", {"company": doc.company,
                "platform": tpl["platform"], "scope": tpl["demographics"]["scope"], "dimension": dim})
            for i in range(1, len(s)):
                if not s[i] or s[i][0] in (None, ""):
                    continue
                frappe.get_doc({"doctype": "Marketing Demographic", "company": doc.company,
                    "platform": tpl["platform"], "scope": tpl["demographics"]["scope"], "dimension": dim,
                    "label": str(s[i][0]), "value": _num(s[i][1]) if len(s[i]) > 1 else 0, "as_of": mx_d}).insert(ignore_permissions=True)
    frappe.db.set_value("Marketing Upload", doc.name, {"status": "Parsed", "template": tpl["key"],
        "row_count": count, "min_date": mn_d, "max_date": mx_d, "error_log": ""})
    frappe.db.commit()

def _parse_competitor(doc, sheets, tpl):
    rows = _find_sheet(sheets, tpl["sheet"]) or _resolve_sheet(sheets, {"csv": True, "match_cols": tpl["match_cols"]})
    if not rows:
        frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed", "error_log": "Competitor sheet not found."}); return
    # period dates are commonly in the first row
    p_start = p_end = None
    ds = sorted([d for d in (_to_date(x) for x in rows[0]) if d]) if rows else []
    if len(ds) >= 1:
        p_start, p_end = ds[0], ds[-1]
    hr = _header_row(rows, tpl["match_cols"]); header = rows[hr]
    c_page = _col(header, "page"); c_nf = _col(header, "new follower")
    c_posts = _col(header, "post"); c_comm = _col(header, "comment"); c_react = _col(header, "reaction")
    count = 0
    for i in range(hr + 1, len(rows)):
        if not rows[i] or c_page is None or str(rows[i][c_page]).strip() in ("", "None"):
            continue
        page = str(rows[i][c_page]).strip()
        frappe.db.delete("Marketing Competitor Snapshot", {"company": doc.company, "competitor": page,
            "platform": tpl["platform"], "period_end": p_end})
        frappe.get_doc({"doctype": "Marketing Competitor Snapshot", "company": doc.company, "competitor": page,
            "platform": tpl["platform"], "period_start": p_start, "period_end": p_end,
            "new_followers": _num(rows[i][c_nf]) if c_nf is not None else 0,
            "posts": _num(rows[i][c_posts]) if c_posts is not None else 0,
            "comments": _num(rows[i][c_comm]) if c_comm is not None else 0,
            "reactions": _num(rows[i][c_react]) if c_react is not None else 0,
            "source": "Upload"}).insert(ignore_permissions=True)
        # ensure a Marketing Competitor record exists (rationale/mapping filled in later)
        if not frappe.db.exists("Marketing Competitor", {"company": doc.company, "competitor_name": page, "platform": tpl["platform"]}):
            frappe.get_doc({"doctype": "Marketing Competitor", "company": doc.company, "competitor_name": page,
                "platform": tpl["platform"], "is_active": 1, "source": "Upload"}).insert(ignore_permissions=True)
        count += 1
    frappe.db.set_value("Marketing Upload", doc.name, {"status": "Parsed", "template": tpl["key"],
        "row_count": count, "min_date": p_start, "max_date": p_end, "error_log": ""})
    frappe.db.commit()

def _upsert_metric(company, d, platform, metric_name, value, source):
    name = frappe.db.get_value("Marketing Metric",
        {"company": company, "date": d, "metric_name": metric_name}, "name")
    if name:
        frappe.db.set_value("Marketing Metric", name, {"value": value, "source": source, "platform": platform})
    else:
        frappe.get_doc({"doctype": "Marketing Metric", "company": company, "date": d,
            "platform": platform, "metric_name": metric_name, "value": value, "source": source}).insert(ignore_permissions=True)
