# Copyright (c) 2026, Kreatao and contributors
import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.title = "My Care Card"
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/my-card"
		raise frappe.Redirect
	context.currency = frappe.db.get_value("Care Card Program",
		frappe.db.get_single_value("Care Card Settings", "default_program"), "currency") or "OMR"
	return context
