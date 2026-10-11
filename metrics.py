"""Metric taxonomy: kind (flow / rate / score) and how a monthly target is derived
from an annual target. Fixes the v0.1 flaw where every monthly target was annual / 12,
which is wrong for scores, rates and ramped run-rate targets."""

# kind: "flow"  -> accumulates; a yearly total can be split across months
#       "rate"  -> a standing level (%, ratio); NOT divided
#       "score" -> a level that climbs from a baseline to the target over the year
METRIC_KIND = {
    # LinkedIn
    "linkedin.impressions": "flow", "linkedin.likes": "flow", "linkedin.comments": "flow",
    "linkedin.reposts": "flow", "linkedin.clicks": "flow", "linkedin.newFollowers": "flow",
    "linkedin.pageViews": "flow", "linkedin.uniqueVisitors": "flow",
    "linkedin.engagementRate": "rate",
    # Other social
    "facebook.newFollowers": "flow", "facebook.likes": "flow", "facebook.shares": "flow", "facebook.comments": "flow",
    "tiktok.newFollowers": "flow", "tiktok.views": "flow", "tiktok.likes": "flow", "tiktok.shares": "flow",
    "instagram.newFollowers": "flow", "instagram.reach": "flow", "instagram.likes": "flow", "instagram.engagementRate": "rate",
    "x.newFollowers": "flow", "x.impressions": "flow", "x.engagementRate": "rate",
    "youtube.subscribers": "flow", "youtube.views": "flow",
    # Website (GA4)
    "website.visitors": "flow", "website.organicShare": "rate",
    # SEO & GEO (Search Console / audits)
    "seogeo.techSeo": "score", "seogeo.onpageSeo": "score", "seogeo.geoScore": "score",
    "seogeo.kwTop10En": "score", "seogeo.kwTop10Ar": "score", "seogeo.aiMention": "rate",
    "seogeo.searchClicks": "flow", "seogeo.searchImpressions": "flow",
    # Outcomes
    "overall.leads": "flow", "overall.conversions": "flow", "overall.revenue": "flow",
}

# Default distribution per kind. All are overridable per metric at save time.
#   even  -> monthly = annual / 12                       (yearly total split evenly)
#   ramp  -> monthly_m = baseline + (annual-baseline)*m/12; month 12 == annual
#   flat  -> monthly = annual                            (a standing level every month)
DEFAULT_DISTRIBUTION = {"flow": "even", "rate": "flat", "score": "ramp"}

# Metrics whose annual target is really a MONTH-12 run-rate (not a yearly sum) — ramp, don't split.
RUN_RATE_FLOWS = {
    "linkedin.impressions", "linkedin.likes", "linkedin.comments", "linkedin.reposts",
    "linkedin.newFollowers", "facebook.newFollowers", "facebook.likes", "tiktok.newFollowers",
    "tiktok.views", "website.visitors",
}

VALID_DISTRIBUTIONS = {"even", "ramp", "flat", "manual"}

def metric_kind(metric_name):
    return METRIC_KIND.get(metric_name, "flow")

def is_rate_or_score(metric_name):
    return metric_kind(metric_name) in ("rate", "score")

def default_distribution(metric_name):
    """Best-fit distribution for a metric if the caller doesn't specify one."""
    if metric_name in RUN_RATE_FLOWS:
        return "ramp"
    return DEFAULT_DISTRIBUTION.get(metric_kind(metric_name), "even")

def monthly_from_annual(annual, baseline, distribution, month):
    """Return the suggested monthly target for month (1..12)."""
    a = float(annual or 0)
    b = float(baseline or 0)
    if distribution == "flat":
        return round(a, 2)
    if distribution == "ramp":
        return round(b + (a - b) * (month / 12.0), 2)
    # even (default for yearly-total flows)
    return round(a / 12.0, 2)

def aggregate(values, metric_name):
    """Aggregate a list of daily/period values: sum for flows, average for rate/score."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if is_rate_or_score(metric_name):
        return round(sum(vals) / len(vals), 2)
    return round(sum(vals), 2)
