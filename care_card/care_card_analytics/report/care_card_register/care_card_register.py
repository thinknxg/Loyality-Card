# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	conditions = ["1=1"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("c.activation_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})
	if filters.get("tier"):
		conditions.append("c.tier = %(tier)s")
		values["tier"] = filters["tier"]
	if filters.get("status"):
		conditions.append("c.status = %(status)s")
		values["status"] = filters["status"]

	rows = frappe.db.sql("""
		select c.name, c.card_number, c.member_name, c.tier, c.status,
			c.mobile_whatsapp, c.source_channel, c.sold_at_location,
			c.activation_date, c.expiry_date,
			(select count(*) from `tabCare Card Dependent` d
				where d.parent = c.name and d.is_active = 1) as dependents,
			c.total_fees_paid, c.total_benefit, c.utilization_ratio, c.visit_count
		from `tabCare Card` c
		where {where}
		order by c.activation_date desc, c.name desc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	columns = [
		{"fieldname": "name", "label": _("Card"), "fieldtype": "Link",
			"options": "Care Card", "width": 130},
		{"fieldname": "card_number", "label": _("Card Number"), "fieldtype": "Data", "width": 150},
		{"fieldname": "member_name", "label": _("Member"), "fieldtype": "Data", "width": 180},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Link",
			"options": "Care Card Tier", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "mobile_whatsapp", "label": _("WhatsApp"), "fieldtype": "Data", "width": 120},
		{"fieldname": "source_channel", "label": _("Channel"), "fieldtype": "Data", "width": 120},
		{"fieldname": "sold_at_location", "label": _("Sold At"), "fieldtype": "Link",
			"options": "Care Participating Location", "width": 130},
		{"fieldname": "activation_date", "label": _("Activated"), "fieldtype": "Date", "width": 100},
		{"fieldname": "expiry_date", "label": _("Expires"), "fieldtype": "Date", "width": 100},
		{"fieldname": "dependents", "label": _("Family"), "fieldtype": "Int", "width": 70},
		{"fieldname": "total_fees_paid", "label": _("Fees Paid"), "fieldtype": "Currency",
			"width": 110},
		{"fieldname": "total_benefit", "label": _("Benefit Availed"), "fieldtype": "Currency",
			"width": 130},
		{"fieldname": "utilization_ratio", "label": _("Utilization %"), "fieldtype": "Percent",
			"width": 110},
		{"fieldname": "visit_count", "label": _("Visits"), "fieldtype": "Int", "width": 70},
	]
	return columns, rows
