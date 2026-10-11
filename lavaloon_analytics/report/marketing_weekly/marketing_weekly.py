import frappe
from lavaloon_analytics import metrics as M

def execute(filters=None):
    filters = filters or {}
    company = filters.get("company"); metric = filters.get("metric_name") or "linkedin.impressions"
    cond = [["company","=",company],["metric_name","=",metric]]
    if filters.get("from_date"): cond.append(["date",">=",filters["from_date"]])
    if filters.get("to_date"): cond.append(["date","<=",filters["to_date"]])
    rows = frappe.get_all("Marketing Metric", filters=cond, fields=["date","value"], limit_page_length=0) if company else []
    buckets = {}
    for r in rows:
        d = frappe.utils.getdate(r.date)
        wk = frappe.utils.getdate(frappe.utils.add_days(d, -(d.weekday()))).isoformat()
        buckets.setdefault(wk, []).append(r.value or 0)
    columns = [
        {"label":"Week of","fieldname":"week","fieldtype":"Date","width":120},
        {"label":"Value","fieldname":"value","fieldtype":"Float","width":120},
        {"label":"WoW change","fieldname":"wow","fieldtype":"Float","width":120},
        {"label":"WoW %","fieldname":"wowpct","fieldtype":"Percent","width":110},
    ]
    data = []; prev = None
    for wk in sorted(buckets):
        v = M.aggregate(buckets[wk], metric)
        wow = (v - prev) if (prev is not None and v is not None) else None
        wowpct = (wow / prev * 100.0) if (wow is not None and prev) else None
        data.append({"week": wk, "value": v, "wow": wow, "wowpct": wowpct}); prev = v
    return columns, data
