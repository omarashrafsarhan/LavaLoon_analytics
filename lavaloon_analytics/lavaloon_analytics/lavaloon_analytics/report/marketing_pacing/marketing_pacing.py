import frappe

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def execute(filters=None):
    filters = filters or {}
    company = filters.get("company"); year = int(filters.get("fiscal_year") or frappe.utils.nowdate()[:4])
    metric = filters.get("metric_name") or "overall.leads"
    columns = [
        {"label": "Month", "fieldname": "month", "fieldtype": "Data", "width": 90},
        {"label": "Target", "fieldname": "target", "fieldtype": "Float", "width": 110},
        {"label": "Actual", "fieldname": "actual", "fieldtype": "Float", "width": 110},
        {"label": "Variance", "fieldname": "variance", "fieldtype": "Float", "width": 110},
        {"label": "% Achieved", "fieldname": "pct", "fieldtype": "Percent", "width": 110},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]
    data = []
    for m in range(1, 13):
        actual = frappe.db.sql("""select sum(value) from `tabMarketing Metric`
            where company=%s and metric_name=%s and year(date)=%s and month(date)=%s""",
            (company, metric, year, m))[0][0] or 0
        target = frappe.db.get_value("Marketing Target",
            {"company": company, "period_type": "Monthly", "fiscal_year": year, "month": m, "metric_name": metric}, "target_value") or 0
        pct = (actual / target * 100.0) if target else None
        status = "" if pct is None else ("Ahead" if pct >= 105 else ("Behind" if pct < 90 else "On track"))
        data.append({"month": MONTHS[m-1], "target": target, "actual": actual,
                     "variance": actual - target, "pct": pct, "status": status})
    return columns, data
