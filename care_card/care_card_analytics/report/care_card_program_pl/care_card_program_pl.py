# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	conditions = ["l.is_cancelled = 0"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("l.posting_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})
	if filters.get("tier"):
		conditions.append("l.tier = %(tier)s")
		values["tier"] = filters["tier"]

	group = "date_format(l.posting_date, '%%Y-%%m')"
	rows = frappe.db.sql("""
		select {group} as period, l.tier,
			sum(case when l.entry_type = 'Fee Collected' then l.amount else 0 end) as fees,
			sum(case when l.entry_type = 'Discount Given' then abs(l.amount) else 0 end) as discount,
			sum(case when l.entry_type = 'Co-pay Shared' then abs(l.amount) else 0 end) as copay,
			sum(case when l.entry_type = 'Refund' then abs(l.amount) else 0 end) as refunds,
			sum(l.margin_cost) as economic_cost
		from `tabCare Card Ledger Entry` l
		where {where}
		group by period, l.tier
		order by period asc
	""".format(group=group, where=" and ".join(conditions)), values, as_dict=True)

	for row in rows:
		row["availed"] = flt(row.discount) + flt(row.copay)
		row["contribution"] = flt(row.fees) - flt(row.economic_cost) - flt(row.refunds)
		row["margin_percent"] = (row["contribution"] / flt(row.fees) * 100.0) if flt(row.fees) else 0

	columns = [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 100},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Link",
			"options": "Care Card Tier", "width": 100},
		{"fieldname": "fees", "label": _("Fee Revenue"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "discount", "label": _("Discount Given"), "fieldtype": "Currency",
			"width": 130},
		{"fieldname": "copay", "label": _("Co-pay Shared"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "availed", "label": _("Total Availed"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "economic_cost", "label": _("Economic Cost"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "refunds", "label": _("Refunds"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "contribution", "label": _("Contribution"), "fieldtype": "Currency",
			"width": 130},
		{"fieldname": "margin_percent", "label": _("Margin %"), "fieldtype": "Percent",
			"width": 100},
	]

	chart = {
		"data": {
			"labels": [r.period for r in rows],
			"datasets": [
				{"name": _("Fees"), "values": [flt(r.fees) for r in rows]},
				{"name": _("Economic Cost"), "values": [flt(r.economic_cost) for r in rows]},
				{"name": _("Contribution"), "values": [flt(r.contribution) for r in rows]},
			],
		},
		"type": "line",
	}
	return columns, rows, None, chart
