import frappe, json
from lavaloon_analytics import metrics as M


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
def save_targets(company, fiscal_year, annual="{}", monthly="{}", distribution="{}", baselines="{}"):
    """Save annual + 12 monthly targets.

    annual:       {metric: annual_value}
    monthly:      {metric: [12 values]}  -- any non-empty cell is a manual override
    distribution: {metric: "even"|"ramp"|"flat"}  -- optional; defaults per metric kind
    baselines:    {metric: baseline_value}        -- ramp start (defaults 0)

    This replaces the v0.1 behaviour of always using annual/12, which was wrong for
    scores, rates and ramped run-rate targets.
    """
    _guard(company)
    annual = json.loads(annual) if isinstance(annual, str) else annual
    monthly = json.loads(monthly) if isinstance(monthly, str) else monthly
    distribution = json.loads(distribution) if isinstance(distribution, str) else distribution
    baselines = json.loads(baselines) if isinstance(baselines, str) else baselines
    fy = int(fiscal_year)

    def put(period, month, metric, val, auto, kind, dist, baseline):
        f = {"company": company, "period_type": period, "fiscal_year": fy, "metric_name": metric}
        if month:
            f["month"] = month
        existing = frappe.db.get_value("Marketing Target", f, "name")
        payload = {"target_value": float(val), "is_auto_suggested": auto,
                   "metric_kind": kind, "distribution": dist, "baseline_value": float(baseline or 0)}
        if existing:
            frappe.db.set_value("Marketing Target", existing, payload)
        else:
            d = dict(f); d.update({"doctype": "Marketing Target"}); d.update(payload)
            frappe.get_doc(d).insert()

    for metric, v in annual.items():
        kind = M.metric_kind(metric)
        dist = (distribution.get(metric) or M.default_distribution(metric))
        if dist not in M.VALID_DISTRIBUTIONS:
            dist = M.default_distribution(metric)
        base = baselines.get(metric, 0)
        put("Annual", None, metric, v, 0, kind, dist, base)
        prov = monthly.get(metric) or []
        for m in range(1, 13):
            manual = len(prov) >= m and prov[m - 1] not in (None, "")
            mv = float(prov[m - 1]) if manual else M.monthly_from_annual(v, base, dist, m)
            put("Monthly", m, metric, mv, 0 if manual else 1, kind, ("manual" if manual else dist), base)
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
        totals.setdefault(r.metric_name, []).append(r.value or 0)
    headline = {mn: M.aggregate(vals, mn) for mn, vals in totals.items()}
    return {"company": company, "metrics": headline, "range": {
        "min": min([str(r.date) for r in rows]) if rows else None,
        "max": max([str(r.date) for r in rows]) if rows else None}}


def _bucket_key(d, granularity):
    d = frappe.utils.getdate(d)
    if granularity == "daily":
        return d.isoformat()
    if granularity == "weekly":
        # ISO week -> Monday of that week
        monday = frappe.utils.add_days(d, -(d.weekday()))
        return frappe.utils.getdate(monday).isoformat()
    # monthly
    return "%04d-%02d" % (d.year, d.month)


@frappe.whitelist()
def get_trend(company, metric_name, granularity="weekly", from_date=None, to_date=None):
    """Time series for one metric at daily / weekly / monthly granularity.
    Flows are summed per bucket; rates/scores are averaged (kind-aware)."""
    _guard(company)
    if granularity not in ("daily", "weekly", "monthly"):
        granularity = "weekly"
    filters = [["company", "=", company], ["metric_name", "=", metric_name]]
    if from_date:
        filters.append(["date", ">=", from_date])
    if to_date:
        filters.append(["date", "<=", to_date])
    rows = frappe.get_all("Marketing Metric", filters=filters, fields=["date", "value"], limit_page_length=0)
    buckets = {}
    for r in rows:
        buckets.setdefault(_bucket_key(r.date, granularity), []).append(r.value or 0)
    series = [{"period": k, "value": M.aggregate(v, metric_name)} for k, v in sorted(buckets.items())]
    return {"company": company, "metric": metric_name, "granularity": granularity, "series": series}
