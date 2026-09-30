import frappe

def scheduled_sync():
    s = frappe.get_single("LavaLoon Analytics Settings")
    if s.crm_sync_enabled and s.sync_company:
        sync_company_crm(s.sync_company)

@frappe.whitelist()
def run_crm_sync(company=None):
    frappe.only_for(["System Manager", "Analytics Manager"])
    s = frappe.get_single("LavaLoon Analytics Settings")
    sync_company_crm(company or s.sync_company)
    return {"ok": True}

def sync_company_crm(company):
    s = frappe.get_single("LavaLoon Analytics Settings")
    lead_dt, deal_dt = s.lead_doctype or "CRM Lead", s.deal_doctype or "CRM Deal"
    if not frappe.db.exists("DocType", lead_dt):
        frappe.log_error("Frappe CRM not found: " + lead_dt, "LavaLoon Analytics CRM sync")
        return
    # Leads per month (by creation)
    _agg_by_month(company, lead_dt, "creation", None, None, None, "overall.leads")
    if frappe.db.exists("DocType", deal_dt):
        status_f, won = s.deal_status_field or "status", s.deal_won_status or "Won"
        # Conversions = won deals per month; Revenue = sum of revenue field on won deals
        _agg_by_month(company, deal_dt, "creation", status_f, won, None, "overall.conversions")
        _agg_by_month(company, deal_dt, "creation", status_f, won, s.revenue_field or "deal_value", "overall.revenue")
    frappe.db.set_single_value("LavaLoon Analytics Settings", "last_sync", frappe.utils.now())
    frappe.db.commit()

def _agg_by_month(company, doctype, date_field, status_field, status_value, sum_field, metric_name):
    filters = {}
    if status_field and status_value:
        filters[status_field] = status_value
    fields = [date_field] + ([sum_field] if sum_field else [])
    try:
        rows = frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=0)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "LavaLoon Analytics CRM agg: " + doctype)
        return
    buckets = {}
    for r in rows:
        dt = r.get(date_field)
        if not dt:
            continue
        key = frappe.utils.getdate(dt).replace(day=1)
        buckets.setdefault(key, 0.0)
        buckets[key] += float(r.get(sum_field) or 0) if sum_field else 1.0
    for d, val in buckets.items():
        name = frappe.db.get_value("Marketing Metric",
            {"company": company, "date": d, "metric_name": metric_name}, "name")
        if name:
            frappe.db.set_value("Marketing Metric", name, {"value": val, "source": "Frappe CRM"})
        else:
            frappe.get_doc({"doctype": "Marketing Metric", "company": company, "date": d,
                "platform": "Overall", "metric_name": metric_name, "value": val, "source": "Frappe CRM"}).insert(ignore_permissions=True)
