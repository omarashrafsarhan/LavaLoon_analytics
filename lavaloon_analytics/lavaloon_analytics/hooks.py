app_name = "lavaloon_analytics"
app_title = "LavaLoon Analytics"
app_publisher = "LavaLoon"
app_description = "Multi-brand social & content analytics: ingest exports or Frappe CRM, track KPIs vs targets."
app_email = "info@lavaloon.com"
app_license = "Proprietary"
app_version = "0.1.0"

after_install = "lavaloon_analytics.install.after_install"

doc_events = {
    "Marketing Upload": {"after_insert": "lavaloon_analytics.ingest.parse_upload"},
}

scheduler_events = {
    "daily": ["lavaloon_analytics.crm_sync.scheduled_sync"],
}
