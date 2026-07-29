# Copyright (c) 2026, Kreatao and contributors
import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.title = "Care Card"
	program = frappe.db.get_single_value("Care Card Settings", "default_program")
	context.program = frappe.get_cached_doc("Care Card Program", program) if program else None
	context.tiers = []
	if program:
		for name in frappe.get_all("Care Card Tier",
				filters={"is_active": 1, "program": program},
				order_by="sort_order asc", pluck="name"):
			context.tiers.append(frappe.get_cached_doc("Care Card Tier", name))
	context.currency = (context.program.currency if context.program else "OMR")
	return context
