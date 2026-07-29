# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	conditions = ["u.docstatus = 1"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("u.posting_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})
	if filters.get("card"):
		conditions.append("u.card = %(card)s")
		values["card"] = filters["card"]
	if filters.get("tier"):
		conditions.append("u.tier = %(tier)s")
		values["tier"] = filters["tier"]
	if filters.get("location"):
		conditions.append("u.location = %(location)s")
		values["location"] = filters["location"]

	rows = frappe.db.sql("""
		select u.name, u.posting_date, u.card, u.member_name, u.beneficiary_name,
			u.beneficiary_code, u.tier, u.location, u.channel, u.source_doctype,
			u.source_docname, u.gross_amount, u.total_discount, u.copay_shared,
			u.net_amount, u.economic_cost, u.insurance_company
		from `tabCare Card Usage` u
		where {where}
		order by u.posting_date desc, u.creation desc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	columns = [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "name", "label": _("Usage"), "fieldtype": "Link",
			"options": "Care Card Usage", "width": 130},
		{"fieldname": "card", "label": _("Card"), "fieldtype": "Link",
			"options": "Care Card", "width": 120},
		{"fieldname": "member_name", "label": _("Member"), "fieldtype": "Data", "width": 150},
		{"fieldname": "beneficiary_name", "label": _("Beneficiary"), "fieldtype": "Data",
			"width": 150},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Data", "width": 80},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Link",
			"options": "Care Participating Location", "width": 130},
		{"fieldname": "channel", "label": _("Channel"), "fieldtype": "Data", "width": 100},
		{"fieldname": "source_docname", "label": _("Bill"), "fieldtype": "Data", "width": 130},
		{"fieldname": "gross_amount", "label": _("Gross"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "total_discount", "label": _("Discount"), "fieldtype": "Currency",
			"width": 110},
		{"fieldname": "copay_shared", "label": _("Co-pay Shared"), "fieldtype": "Currency",
			"width": 120},
		{"fieldname": "net_amount", "label": _("Net"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "economic_cost", "label": _("Economic Cost"), "fieldtype": "Currency",
			"width": 130},
	]
	return columns, rows
