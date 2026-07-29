# Copyright (c) 2026, Kreatao and contributors
"""Utilization, breakeven and program economics — all read from the ledger."""

import frappe
from frappe.utils import flt, getdate

from care_card.ledger import balances


def margin_factor_for(category):
	if not category:
		return 100.0
	value = frappe.db.get_value("Care Benefit Category", category, "margin_factor")
	return flt(value if value is not None else 100)


def breakeven_date(card):
	"""First date on which cumulative benefit granted reached the fees paid."""
	rows = frappe.get_all("Care Card Ledger Entry",
		filters={"card": card, "is_cancelled": 0},
		fields=["posting_date", "entry_type", "amount"],
		order_by="posting_date asc, creation asc")
	fees = benefit = 0.0
	for row in rows:
		if row.entry_type == "Fee Collected":
			fees += flt(row.amount)
		elif row.entry_type in ("Discount Given", "Co-pay Shared", "Adjustment"):
			benefit += abs(flt(row.amount))
		elif row.entry_type == "Reversal":
			benefit -= abs(flt(row.amount))
		if fees > 0 and benefit >= fees:
			return row.posting_date
	return None


@frappe.whitelist()
def refresh_card(card):
	"""Recompute the cached utilization fields on a Care Card."""
	if not frappe.db.exists("Care Card", card):
		return
	bal = balances(card)
	visits = frappe.db.sql("""
		select count(distinct name) as visits, max(posting_date) as last_visit
		from `tabCare Card Usage` where card=%s and docstatus=1
	""", card, as_dict=True)
	visit_count = flt(visits[0].visits) if visits else 0
	last_visit = visits[0].last_visit if visits else None

	total_benefit = bal["total_benefit"]
	fees = bal["fees"]
	ratio = (total_benefit / fees * 100.0) if fees else 0.0

	frappe.db.set_value("Care Card", card, {
		"total_fees_paid": fees,
		"total_discount_availed": bal["discount"],
		"total_copay_shared": bal["copay"],
		"total_benefit": total_benefit,
		"economic_cost": bal["economic_cost"],
		"utilization_ratio": ratio,
		"visit_count": visit_count,
		"last_visit_date": last_visit,
		"breakeven_date": breakeven_date(card),
	}, update_modified=False)
	return True


@frappe.whitelist()
def card_summary(card):
	"""Everything the member portal and the desk need in one call."""
	doc = frappe.get_doc("Care Card", card)
	bal = balances(card)
	usage = frappe.get_all("Care Card Usage",
		filters={"card": card, "docstatus": 1},
		fields=["name", "posting_date", "beneficiary_name", "location", "gross_amount",
			"total_discount", "copay_shared", "net_amount"],
		order_by="posting_date desc", limit=50)
	by_category = frappe.get_all("Care Card Ledger Entry",
		filters={"card": card, "is_cancelled": 0,
			"entry_type": ["in", ["Discount Given", "Co-pay Shared"]]},
		fields=["benefit_category", "sum(amount) as amount"],
		group_by="benefit_category")
	return {
		"card": doc.as_dict(),
		"balances": bal,
		"usage": usage,
		"by_category": [{"category": r.benefit_category, "amount": abs(flt(r.amount))}
			for r in by_category],
		"breakeven_percent": round(
			(bal["total_benefit"] / bal["fees"] * 100.0) if bal["fees"] else 0.0, 1),
	}


@frappe.whitelist()
def program_summary(from_date=None, to_date=None, tier=None):
	"""Program level economics for the workspace and the weekly digest."""
	conditions = ["1=1"]
	values = {}
	if from_date and to_date:
		conditions.append("l.posting_date between %(from_date)s and %(to_date)s")
		values.update({"from_date": from_date, "to_date": to_date})
	if tier:
		conditions.append("l.tier = %(tier)s")
		values["tier"] = tier
	where = " and ".join(conditions)

	rows = frappe.db.sql("""
		select l.entry_type, sum(l.amount) as amount, sum(l.margin_cost) as margin_cost
		from `tabCare Card Ledger Entry` l
		where l.is_cancelled = 0 and {where}
		group by l.entry_type
	""".format(where=where), values, as_dict=True)

	out = {"fees": 0.0, "discount": 0.0, "copay": 0.0, "economic_cost": 0.0}
	for row in rows:
		out["economic_cost"] += flt(row.margin_cost)
		if row.entry_type == "Fee Collected":
			out["fees"] += flt(row.amount)
		elif row.entry_type == "Discount Given":
			out["discount"] += abs(flt(row.amount))
		elif row.entry_type == "Co-pay Shared":
			out["copay"] += abs(flt(row.amount))

	out["total_benefit"] = out["discount"] + out["copay"]
	out["contribution"] = out["fees"] - out["economic_cost"]
	out["active_cards"] = frappe.db.count("Care Card", {"status": "Active"})
	out["past_breakeven"] = frappe.db.count("Care Card",
		{"breakeven_date": ["is", "set"], "status": "Active"})
	out["expiring_30"] = frappe.db.sql("""
		select count(*) from `tabCare Card`
		where status='Active' and expiry_date between curdate() and date_add(curdate(), interval 30 day)
	""")[0][0]
	return out
