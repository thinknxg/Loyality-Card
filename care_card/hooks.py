app_name = "care_card"
app_title = "Care Card"
app_publisher = "Kreatao"
app_description = "Hospital & Pharmacy Subscription Card Program"
app_email = "info@kreatao.com"
app_license = "MIT"
app_version = "1.0.0"

# ERPNext is optional: hooks below simply never fire when the doctype is absent,
# so the app installs and runs on a bare Frappe bench (external HIS / KareXpert mode).
# required_apps = ["erpnext"]

# ------------------------------------------------------------------ assets
app_include_css = "/assets/care_card/css/care_card.css"
app_include_js = "/assets/care_card/js/care_card.js"

web_include_css = "/assets/care_card/css/portal.css"

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "POS Invoice": "public/js/sales_invoice.js",
}

# ------------------------------------------------------------------ portal
website_route_rules = [
    {"from_route": "/my-card/<path:app_path>", "to_route": "my-card"},
]

website_context = {
    "favicon": "/assets/care_card/images/favicon.svg",
}

# -------------------------------------------------------------- installers
after_install = "care_card.install.after_install"
before_uninstall = "care_card.install.before_uninstall"

# ------------------------------------------------------------------ events
doc_events = {
    "Sales Invoice": {
        "before_validate": "care_card.engine.hooks_billing.before_validate",
        "on_submit": "care_card.engine.hooks_billing.on_submit",
        "on_cancel": "care_card.engine.hooks_billing.on_cancel",
    },
    "POS Invoice": {
        "before_validate": "care_card.engine.hooks_billing.before_validate",
        "on_submit": "care_card.engine.hooks_billing.on_submit",
        "on_cancel": "care_card.engine.hooks_billing.on_cancel",
    },
    "Payment Entry": {
        "on_submit": "care_card.engine.hooks_billing.payment_on_submit",
    },
}

# --------------------------------------------------------------- scheduler
scheduler_events = {
    "cron": {
        "*/15 * * * *": [
            "care_card.tasks.drain_message_queue",
        ],
    },
    "hourly_long": [
        "care_card.tasks.poll_delivery_receipts",
    ],
    "daily_long": [
        "care_card.tasks.expire_cards",
        "care_card.tasks.send_renewal_reminders",
        "care_card.tasks.refresh_card_analytics",
    ],
    "weekly_long": [
        "care_card.tasks.management_digest",
    ],
}

# ------------------------------------------------------- permission queries
permission_query_conditions = {
    "Care Card": "care_card.permissions.care_card_query",
    "Care Card Usage": "care_card.permissions.usage_query",
    "Care Card Ledger Entry": "care_card.permissions.ledger_query",
}

has_permission = {
    "Care Card": "care_card.permissions.care_card_has_permission",
}

# ---------------------------------------------------------------- fixtures
fixtures = [
    {"dt": "Custom Field", "filters": [["module", "=", "Care Card Setup"]]},
    {"dt": "Property Setter", "filters": [["module", "=", "Care Card Setup"]]},
]

# ---------------------------------------------------------------- jinja
jinja = {
    "methods": [
        "care_card.utils.formatting.fmt_currency",
        "care_card.utils.formatting.fmt_date",
    ]
}
