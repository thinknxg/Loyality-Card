# Copyright (c) 2026, Kreatao and contributors
"""Scheduled jobs."""

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from care_card.messaging import queue_event, send


def expire_cards():
	"""Move cards past their last paid term (plus grace) to Expired."""
	rows = frappe.db.sql("""
		select c.name, c.expiry_date, p.grace_period_days
		from `tabCare Card` c
		left join `tabCare Card Program` p on p.name = c.program
		where c.status = 'Active' and c.expiry_date is not null
	""", as_dict=True)
	today = getdate(nowdate())
	for row in rows:
		grace = int(row.grace_period_days or 0)
		if getdate(add_days(row.expiry_date, grace)) < today:
			frappe.db.set_value("Care Card", row.name, "status", "Expired",
				update_modified=False)
			queue_event(row.name, "Card Expired")
	frappe.db.commit()


def send_renewal_reminders():
	"""One reminder per configured offset, deduplicated by day."""
	programs = frappe.get_all("Care Card Program", filters={"is_active": 1}, pluck="name")
	today = getdate(nowdate())
	for program in programs:
		schedule = frappe.get_all("Care Card Reminder Schedule",
			filters={"parent": program, "parenttype": "Care Card Program", "is_active": 1},
			fields=["days_before_expiry", "channel", "message_template"])
		for rule in schedule:
			target = add_days(today, int(rule.days_before_expiry or 0))
			cards = frappe.get_all("Care Card",
				filters={"program": program, "status": "Active", "expiry_date": target,
					"auto_renew": 1},
				pluck="name")
			for card in cards:
				already = frappe.db.sql("""
					select name from `tabCare Card Message Log`
					where card=%s and event='Renewal Reminder' and date(creation)=curdate()
					limit 1
				""", card)
				if already:
					continue
				queue_event(card, "Renewal Reminder",
					extra={"days_left": rule.days_before_expiry},
					channel=rule.channel or "WhatsApp")
	frappe.db.commit()


def refresh_card_analytics():
	from care_card.analytics import refresh_card

	names = frappe.get_all("Care Card",
		filters={"status": ["in", ["Active", "Expired", "Suspended"]]}, pluck="name")
	for name in names:
		try:
			refresh_card(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Care Card: analytics refresh failed")
	frappe.db.commit()


def drain_message_queue():
	limit = frappe.db.get_single_value("Care Card Settings", "message_retry_limit") or 3
	rows = frappe.get_all("Care Card Message Log",
		filters={"status": ["in", ["Queued", "Failed"]], "retry_count": ["<", limit]},
		pluck="name", limit=200, order_by="creation asc")
	for name in rows:
		send(name)
	frappe.db.commit()


def poll_delivery_receipts():
	from care_card.integrations.whatsapp import poll_receipts

	try:
		poll_receipts()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Care Card: receipt polling failed")


def management_digest():
	"""Weekly summary to Care Card Managers."""
	from care_card.analytics import program_summary

	recipients = frappe.get_all("Has Role", filters={"role": "Care Card Manager",
		"parenttype": "User"}, pluck="parent")
	recipients = [r for r in recipients if frappe.db.get_value("User", r, "enabled")]
	if not recipients:
		return
	summary = program_summary(from_date=add_days(nowdate(), -7), to_date=nowdate())
	rows = "".join(
		"<tr><td style='padding:4px 12px'>%s</td><td style='padding:4px 12px;text-align:right'>%s</td></tr>"
		% (label, round(flt(summary.get(key)), 3))
		for label, key in [
			("Fees collected", "fees"),
			("Discount granted", "discount"),
			("Co-pay shared", "copay"),
			("Economic cost", "economic_cost"),
			("Contribution", "contribution"),
			("Active cards", "active_cards"),
			("Past breakeven", "past_breakeven"),
			("Expiring in 30 days", "expiring_30"),
		])
	frappe.sendmail(
		recipients=recipients,
		subject="Care Card — weekly summary",
		message="<h3>Care Card, last 7 days</h3><table>%s</table>" % rows,
		reference_doctype="Care Card Settings",
	)
