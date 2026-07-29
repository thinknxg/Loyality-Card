# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	conditions = ["c.status != 'Draft'"]
	values = {}
	if filters.get("from_date") and filters.get("to_date"):
		conditions.append("c.activation_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": filters["from_date"], "to_date": filters["to_date"]})

	group_by = "c.issued_by" if filters.get("by_agent") else "c.source_channel"
	rows = frappe.db.sql("""
		select {group} as segment, c.tier,
			count(*) as cards,
			sum(c.total_fees_paid) as fees,
			sum(c.total_benefit) as availed,
			sum(c.economic_cost) as economic_cost,
			avg(c.utilization_ratio) as avg_utilization,
			sum(case when c.breakeven_date is not null then 1 else 0 end) as past_breakeven
		from `tabCare Card` c
		where {where}
		group by segment, c.tier
		order by cards desc
	""".format(group=group_by, where=" and ".join(conditions)), values, as_dict=True)

	for row in rows:
		row["contribution"] = flt(row.fees) - flt(row.economic_cost)
		row["breakeven_rate"] = (flt(row.past_breakeven) / flt(row.cards) * 100.0) \
			if flt(row.cards) else 0

	columns = [
		{"fieldname": "segment", "label": _("Channel / Agent"), "fieldtype": "Data", "width": 200},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Data", "width": 90},
		{"fieldname": "cards", "label": _("Cards Sold"), "fieldtype": "Int", "width": 100},
		{"fieldname": "fees", "label": _("Fee Revenue"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "availed", "label": _("Benefit Availed"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "economic_cost", "label": _("Economic Cost"), "fieldtype": "Currency",
			"width": 140},
		{"fieldname": "contribution", "label": _("Contribution"), "fieldtype": "Currency",
			"width": 130},
		{"fieldname": "avg_utilization", "label": _("Avg Utilization %"), "fieldtype": "Percent",
			"width": 140},
		{"fieldname": "breakeven_rate", "label": _("Past Breakeven %"), "fieldtype": "Percent",
			"width": 140},
	]
	return columns, rows
