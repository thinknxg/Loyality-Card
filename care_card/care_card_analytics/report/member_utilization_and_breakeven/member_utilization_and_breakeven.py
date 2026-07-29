# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _
from frappe.utils import date_diff, flt, nowdate


def execute(filters=None):
	filters = filters or {}
	conditions = ["c.status != 'Draft'"]
	values = {}
	if filters.get("tier"):
		conditions.append("c.tier = %(tier)s")
		values["tier"] = filters["tier"]
	if filters.get("only_past_breakeven"):
		conditions.append("c.breakeven_date is not null")

	rows = frappe.db.sql("""
		select c.name, c.card_number, c.member_name, c.tier, c.status,
			c.activation_date, c.expiry_date, c.total_fees_paid,
			c.total_discount_availed, c.total_copay_shared, c.total_benefit,
			c.economic_cost, c.utilization_ratio, c.breakeven_date,
			c.visit_count, c.last_visit_date
		from `tabCare Card` c
		where {where}
		order by c.utilization_ratio desc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	today = nowdate()
	for row in rows:
		row["contribution"] = flt(row.total_fees_paid) - flt(row.economic_cost)
		if row.breakeven_date and row.activation_date:
			row["days_to_breakeven"] = date_diff(row.breakeven_date, row.activation_date)
		else:
			row["days_to_breakeven"] = None
		elapsed = date_diff(today, row.activation_date) if row.activation_date else 0
		if elapsed > 0 and flt(row.total_benefit):
			row["projected_annual_benefit"] = flt(row.total_benefit) * 365.0 / elapsed
		else:
			row["projected_annual_benefit"] = 0

	columns = [
		{"fieldname": "name", "label": _("Card"), "fieldtype": "Link",
			"options": "Care Card", "width": 130},
		{"fieldname": "member_name", "label": _("Member"), "fieldtype": "Data", "width": 170},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Link",
			"options": "Care Card Tier", "width": 90},
		{"fieldname": "activation_date", "label": _("Activated"), "fieldtype": "Date", "width": 100},
		{"fieldname": "total_fees_paid", "label": _("Fees Paid"), "fieldtype": "Currency",
			"width": 100},
		{"fieldname": "total_discount_availed", "label": _("Discount"), "fieldtype": "Currency",
			"width": 110},
		{"fieldname": "total_copay_shared", "label": _("Co-pay Shared"), "fieldtype": "Currency",
			"width": 120},
		{"fieldname": "total_benefit", "label": _("Total Availed"), "fieldtype": "Currency",
			"width": 120},
		{"fieldname": "economic_cost", "label": _("Economic Cost"), "fieldtype": "Currency",
			"width": 120},
		{"fieldname": "contribution", "label": _("Contribution"), "fieldtype": "Currency",
			"width": 110},
		{"fieldname": "utilization_ratio", "label": _("Utilization %"), "fieldtype": "Percent",
			"width": 110},
		{"fieldname": "breakeven_date", "label": _("Breakeven"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_breakeven", "label": _("Days to BE"), "fieldtype": "Int",
			"width": 100},
		{"fieldname": "projected_annual_benefit", "label": _("Projected / Year"),
			"fieldtype": "Currency", "width": 130},
		{"fieldname": "visit_count", "label": _("Visits"), "fieldtype": "Int", "width": 70},
		{"fieldname": "last_visit_date", "label": _("Last Visit"), "fieldtype": "Date",
			"width": 100},
	]

	fees = sum(flt(r.total_fees_paid) for r in rows)
	cost = sum(flt(r.economic_cost) for r in rows)
	availed = sum(flt(r.total_benefit) for r in rows)
	past = len([r for r in rows if r.breakeven_date])
	summary = [
		{"label": _("Fees Collected"), "value": fees, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Benefit Availed"), "value": availed, "datatype": "Currency",
			"indicator": "Orange"},
		{"label": _("Economic Cost"), "value": cost, "datatype": "Currency", "indicator": "Red"},
		{"label": _("Contribution"), "value": fees - cost, "datatype": "Currency",
			"indicator": "Green" if fees - cost >= 0 else "Red"},
		{"label": _("Past Breakeven"), "value": past, "datatype": "Int", "indicator": "Grey"},
	]
	return columns, rows, None, None, summary
