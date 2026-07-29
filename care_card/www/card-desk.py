# Copyright (c) 2026, Kreatao and contributors
import frappe

no_cache = 1

ALLOWED = {"System Manager", "Care Card Manager", "Care Card Auditor",
	"Care Card Sales Agent", "Care Card Hospital Cashier", "Care Card Pharmacy Cashier"}


def get_context(context):
	context.no_cache = 1
	context.title = "Card Desk"
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/card-desk"
		raise frappe.Redirect
	if not (ALLOWED & set(frappe.get_roles())):
		frappe.throw(frappe._("You do not have access to the card desk."),
			frappe.PermissionError)
	context.tiers = frappe.get_all("Care Card Tier", filters={"is_active": 1},
		fields=["name", "annual_fee"], order_by="sort_order asc")
	context.locations = frappe.get_all("Care Participating Location",
		filters={"is_active": 1}, pluck="name")
	context.currency = frappe.db.get_value("Care Card Program",
		frappe.db.get_single_value("Care Card Settings", "default_program"), "currency") or "OMR"
	return context
