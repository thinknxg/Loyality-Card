# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	conditions = ["u.docstatus = 1", "u.copay_shared > 0"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("u.posting_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})
	if filters.get("insurance_company"):
		conditions.append("u.insurance_company = %(insurance_company)s")
		values["insurance_company"] = filters["insurance_company"]
	if filters.get("tier"):
		conditions.append("u.tier = %(tier)s")
		values["tier"] = filters["tier"]

	rows = frappe.db.sql("""
		select coalesce(u.insurance_company, 'Unspecified') as insurance_company,
			coalesce(u.insurance_plan, '') as insurance_plan, u.tier,
			count(distinct u.name) as visits,
			count(distinct u.card) as cards,
			sum(u.gross_amount) as gross_amount,
			sum(u.copay_shared) as copay_shared,
			sum(u.total_discount) as discount
		from `tabCare Card Usage` u
		where {where}
		group by insurance_company, insurance_plan, u.tier
		order by copay_shared desc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	columns = [
		{"fieldname": "insurance_company", "label": _("Insurer"), "fieldtype": "Data",
			"width": 200},
		{"fieldname": "insurance_plan", "label": _("Plan"), "fieldtype": "Data", "width": 150},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Data", "width": 90},
		{"fieldname": "cards", "label": _("Cards"), "fieldtype": "Int", "width": 80},
		{"fieldname": "visits", "label": _("Visits"), "fieldtype": "Int", "width": 80},
		{"fieldname": "gross_amount", "label": _("Gross Billed"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "copay_shared", "label": _("Co-pay Absorbed"), "fieldtype": "Currency",
			"width": 150},
		{"fieldname": "discount", "label": _("Discount on Uncovered"), "fieldtype": "Currency",
			"width": 170},
	]
	return columns, rows
