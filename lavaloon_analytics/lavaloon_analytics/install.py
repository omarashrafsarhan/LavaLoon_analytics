import frappe

ROLES = ["Analytics Manager", "Analytics Analyst", "Analytics Viewer"]

def after_install():
    for r in ROLES:
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Marketing Company", "LavaLoon"):
        frappe.get_doc({"doctype": "Marketing Company", "company_name": "LavaLoon",
                        "slug": "lavaloon", "color_primary": "#E82528", "color_secondary": "#FAAE43"}).insert(ignore_permissions=True)
    s = frappe.get_single("LavaLoon Analytics Settings")
    if not s.get("deal_won_status"):
        s.deal_won_status = "Won"; s.lead_doctype = "CRM Lead"; s.deal_doctype = "CRM Deal"
        s.deal_status_field = "status"; s.revenue_field = "deal_value"; s.save(ignore_permissions=True)
    frappe.db.commit()
