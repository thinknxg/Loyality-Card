# Copyright (c) 2026, Kreatao and contributors

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate


def execute(filters=None):
	filters = filters or {}
	days = int(filters.get("days") or 60)
	conditions = ["c.status in ('Active', 'Expired')",
		"c.expiry_date is not null",
		"c.expiry_date <= date_add(curdate(), interval %(days)s day)"]
	values = {"days": days}
	if filters.get("tier"):
		conditions.append("c.tier = %(tier)s")
		values["tier"] = filters["tier"]

	rows = frappe.db.sql("""
		select c.name, c.card_number, c.member_name, c.tier, c.status,
			c.mobile_whatsapp, c.expiry_date, c.auto_renew,
			c.total_fees_paid, c.total_benefit, c.utilization_ratio, c.visit_count,
			(select max(m.creation) from `tabCare Card Message Log` m
				where m.card = c.name and m.event = 'Renewal Reminder') as last_reminder
		from `tabCare Card` c
		where {where}
		order by c.expiry_date asc
	""".format(where=" and ".join(conditions)), values, as_dict=True)

	today = nowdate()
	for row in rows:
		row["days_to_expiry"] = date_diff(row.expiry_date, today)
		row["renewal_likelihood"] = ("High" if row.utilization_ratio and row.utilization_ratio >= 100
			else "Medium" if row.visit_count else "Low")

	columns = [
		{"fieldname": "expiry_date", "label": _("Expires"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_expiry", "label": _("Days"), "fieldtype": "Int", "width": 70},
		{"fieldname": "name", "label": _("Card"), "fieldtype": "Link",
			"options": "Care Card", "width": 130},
		{"fieldname": "member_name", "label": _("Member"), "fieldtype": "Data", "width": 170},
		{"fieldname": "mobile_whatsapp", "label": _("WhatsApp"), "fieldtype": "Data", "width": 120},
		{"fieldname": "tier", "label": _("Tier"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "utilization_ratio", "label": _("Utilization %"), "fieldtype": "Percent",
			"width": 110},
		{"fieldname": "visit_count", "label": _("Visits"), "fieldtype": "Int", "width": 70},
		{"fieldname": "renewal_likelihood", "label": _("Likelihood"), "fieldtype": "Data",
			"width": 100},
		{"fieldname": "last_reminder", "label": _("Last Reminder"), "fieldtype": "Datetime",
			"width": 150},
		{"fieldname": "auto_renew", "label": _("Reminders On"), "fieldtype": "Check", "width": 110},
	]
	return columns, rows
