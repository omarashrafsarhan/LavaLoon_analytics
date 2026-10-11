import frappe

def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    cond = {"company": company} if company else {}
    rows = frappe.get_all("Marketing Competitor Snapshot", filters=cond,
        fields=["competitor","platform","period_start","period_end","new_followers","posts","comments","reactions"],
        limit_page_length=0)
    # keep the latest snapshot (by period_end) per competitor
    latest = {}
    for r in rows:
        k = (r.competitor, r.platform)
        if k not in latest or str(r.period_end) > str(latest[k].period_end):
            latest[k] = r
    out = sorted(latest.values(), key=lambda r: -(r.new_followers or 0))
    columns = [
        {"label":"Competitor","fieldname":"competitor","fieldtype":"Data","width":220},
        {"label":"Platform","fieldname":"platform","fieldtype":"Data","width":90},
        {"label":"Period end","fieldname":"period_end","fieldtype":"Date","width":100},
        {"label":"New followers","fieldname":"new_followers","fieldtype":"Float","width":120},
        {"label":"Posts","fieldname":"posts","fieldtype":"Float","width":80},
        {"label":"Comments","fieldname":"comments","fieldtype":"Float","width":90},
        {"label":"Reactions","fieldname":"reactions","fieldtype":"Float","width":90},
        {"label":"React / post","fieldname":"rpp","fieldtype":"Float","width":100},
    ]
    data = []
    for r in out:
        r = dict(r); r["rpp"] = round((r["reactions"] or 0)/r["posts"],1) if r.get("posts") else None
        data.append(r)
    return columns, data
