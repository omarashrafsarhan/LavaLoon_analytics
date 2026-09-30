import frappe, json

RATE = {"linkedin.engagementRate", "seogeo.techSeo", "seogeo.geoScore", "website.organicShare"}


def _guard(company):
    # Tenancy: caller must be allowed to read this Marketing Company (respects role + User Permission).
    frappe.has_permission("Marketing Company", doc=company, ptype="read", throw=True)

@frappe.whitelist()
def add_manual_metrics(company, date, platform, values):
    _guard(company)
    vals = json.loads(values) if isinstance(values, str) else values
    for metric_name, v in vals.items():
        name = frappe.db.get_value("Marketing Metric", {"company": company, "date": date, "metric_name": metric_name}, "name")
        if name:
            frappe.db.set_value("Marketing Metric", name, {"value": v, "source": "Manual", "platform": platform})
        else:
            frappe.get_doc({"doctype": "Marketing Metric", "company": company, "date": date,
                "platform": platform, "metric_name": metric_name, "value": v, "source": "Manual"}).insert()
    frappe.db.commit()
    return {"ok": True, "saved": len(vals)}

@frappe.whitelist()
def save_targets(company, fiscal_year, annual="{}", monthly="{}"):
    _guard(company)
    annual = json.loads(annual) if isinstance(annual, str) else annual
    monthly = json.loads(monthly) if isinstance(monthly, str) else monthly
    fy = int(fiscal_year)
    def put(period, month, metric, val, auto):
        f = {"company": company, "period_type": period, "fiscal_year": fy, "metric_name": metric}
        if month:
            f["month"] = month
        name = frappe.db.get_value("Marketing Target", f, "name")
        if name:
            frappe.db.set_value("Marketing Target", name, {"target_value": val, "is_auto_suggested": auto})
        else:
            d = dict(f); d.update({"doctype": "Marketing Target", "target_value": val, "is_auto_suggested": auto})
            frappe.get_doc(d).insert()
    for metric, v in annual.items():
        put("Annual", None, metric, float(v), 0)
        prov = monthly.get(metric) or []
        for m in range(1, 13):
            mv = prov[m - 1] if len(prov) >= m and prov[m - 1] not in (None, "") else round(float(v) / 12.0, 2)
            put("Monthly", m, metric, float(mv), 0 if (len(prov) >= m and prov[m - 1] not in (None, "")) else 1)
    frappe.db.commit()
    return {"ok": True}

@frappe.whitelist()
def get_dashboard(company, from_date=None, to_date=None):
    _guard(company)
    filters = [["company", "=", company]]
    if from_date:
        filters.append(["date", ">=", from_date])
    if to_date:
        filters.append(["date", "<=", to_date])
    rows = frappe.get_all("Marketing Metric", filters=filters, fields=["date", "metric_name", "value"], limit_page_length=0)
    totals = {}
    for r in rows:
        totals.setdefault(r.metric_name, [])
        totals[r.metric_name].append(r.value or 0)
    def agg(mn):
        v = totals.get(mn, [])
        if not v:
            return None
        return round(sum(v) / len(v), 2) if mn in RATE else round(sum(v), 2)
    headline = {mn: agg(mn) for mn in totals}
    return {"company": company, "metrics": headline, "range": {
        "min": min([str(r.date) for r in rows]) if rows else None,
        "max": max([str(r.date) for r in rows]) if rows else None}}
