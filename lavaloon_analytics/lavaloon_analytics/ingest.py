import frappe, io, datetime, re

# Canonical LinkedIn templates: sheet + column -> namespaced metric
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
    try:
        return frappe.utils.getdate(x)
    except Exception:
        return None

def _load_sheets(filename, content):
    # Returns {sheet_name: list-of-rows(list)}. Supports xlsx via openpyxl and csv.
    name = (filename or "").lower()
    if name.endswith(".csv"):
        import csv
        rows = list(csv.reader(io.StringIO(content.decode("utf-8", "ignore"))))
        return {"Sheet1": rows}
    if name.endswith(".xls"):
        raise ValueError("Legacy .xls files aren't supported. Re-save the export as .xlsx and upload again.")
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    return out

def _find_sheet(sheets, name):
    for k in sheets:
        if str(k).lower() == name.lower() or name.lower() in str(k).lower():
            return sheets[k]
    return None

def _header_row(rows, keys):
    for i in range(min(8, len(rows))):
        low = [str(c).lower() for c in rows[i]]
        if all(any(k in c for c in low) for k in keys):
            return i
    return 0

def _col(header, name):
    for j, c in enumerate(header):
        if name.lower() in str(c).lower():
            return j
    return None

def detect(sheets):
    names = [str(s).lower() for s in sheets]
    cols = set()
    for s in sheets.values():
        for i in range(min(8, len(s))):
            for c in s[i]:
                cols.add(str(c).lower())
    for t in TEMPLATES:
        if any(t["sheet"].lower() in n for n in names) and all(any(mc in c for c in cols) for mc in t["match_cols"]):
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
            frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed", "error_log": "Could not match a known LinkedIn template (Content/Followers/Visitors)."})
            return
        rows = _find_sheet(sheets, tpl["sheet"])
        hr = _header_row(rows, tpl["match_cols"]); header = rows[hr]
        dcol = _col(header, tpl["date_col"])
        colmap = {mn: _col(header, src) for src, mn in tpl["fields"].items()}
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
                _upsert_metric(doc.company, d, tpl["platform"], mn, val, "Upload")
                count += 1
        # demographics
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
        frappe.db.set_value("Marketing Upload", doc.name, {"status": "Parsed", "template": tpl["key"], "row_count": count,
                    "min_date": mn_d, "max_date": mx_d, "error_log": ""})
        frappe.db.commit()
    except Exception:
        frappe.db.set_value("Marketing Upload", doc.name, {"status": "Failed", "error_log": frappe.get_traceback()[-1400:]})
        frappe.db.commit()

def _upsert_metric(company, d, platform, metric_name, value, source):
    name = frappe.db.get_value("Marketing Metric",
        {"company": company, "date": d, "metric_name": metric_name}, "name")
    if name:
        frappe.db.set_value("Marketing Metric", name, {"value": value, "source": source, "platform": platform})
    else:
        frappe.get_doc({"doctype": "Marketing Metric", "company": company, "date": d,
            "platform": platform, "metric_name": metric_name, "value": value, "source": source}).insert(ignore_permissions=True)
