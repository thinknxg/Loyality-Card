# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	conditions = ["l.is_cancelled = 0",
		"l.entry_type in ('Discount Given', 'Co-pay Shared')"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("l.posting_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})
	if filters.get("tier"):
		conditions.append("l.tier = %(tier)s")
		values["tier"] = filters["tier"]

	rows = frappe.db.sql("""
		select coalesce(l.benefit_category, 'Uncategorised') as benefit_category,
			l.tier,
			sum(case when l.entry_type = 'Discount Given' then abs(l.amount) else 0 end) as discount,
			sum(case when l.entry_type = 'Co-pay Shared' then abs(l.amount) else 0 end) as copay,
			sum(l.margin_cost) as economic_cost,
			count(distinct l.card) as cards
		from `tabCare Card Ledger Entry` l
		where {where}
		group by benefit_category, l.tier
		order by economic_cost desc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	for row in rows:
		row["total"] = flt(row.discount) + flt(row.copay)
		row["margin_factor"] = frappe.db.get_value("Care Benefit Category",
			row.benefit_category, "margin_factor") if row.benefit_category != "Uncategorised" else 100

	columns = [
		{"fieldname": "benefit_category", "label": _("Category"), "fieldtype": "Data",
			"width": 200},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Link",
			"options": "Care Card Tier", "width": 100},
		{"fieldname": "discount", "label": _("Discount Given"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "copay", "label": _("Co-pay Shared"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "total", "label": _("Total Availed"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "margin_factor", "label": _("Margin Factor %"), "fieldtype": "Percent",
			"width": 130},
		{"fieldname": "economic_cost", "label": _("Economic Cost"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "cards", "label": _("Cards"), "fieldtype": "Int", "width": 80},
	]

	chart = {
		"data": {
			"labels": [r.benefit_category for r in rows],
			"datasets": [
				{"name": _("Availed"), "values": [flt(r.total) for r in rows]},
				{"name": _("Economic Cost"), "values": [flt(r.economic_cost) for r in rows]},
			],
		},
		"type": "bar",
	}
	return columns, rows, None, chart
