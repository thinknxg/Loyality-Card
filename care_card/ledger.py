# Copyright (c) 2026, Kreatao and contributors
"""The immutable Care Card ledger.

Every movement of value lands here — fees in, discounts out, co-pay shares out.
Nothing is ever edited or deleted; corrections are posted as reversals.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def margin_factor(category):
	if not category:
		return 100.0
	value = frappe.db.get_value("Care Benefit Category", category, "margin_factor")
	return flt(value if value is not None else 100)


def make_entry(card, entry_type, amount, **kwargs):
	"""Insert one ledger entry. ``amount`` is signed by the caller's intent:
	fees are positive, benefits granted are negative."""
	doc = frappe.new_doc("Care Card Ledger Entry")
	doc.card = card
	doc.entry_type = entry_type
	doc.amount = flt(amount)
	doc.posting_date = kwargs.get("posting_date") or nowdate()
	doc.tier = kwargs.get("tier") or frappe.db.get_value("Care Card", card, "tier")
	doc.beneficiary_code = kwargs.get("beneficiary_code")
	doc.benefit_category = kwargs.get("benefit_category")
	doc.reference_doctype = kwargs.get("reference_doctype")
	doc.reference_name = kwargs.get("reference_name")
	doc.location = kwargs.get("location")
	doc.term_no = kwargs.get("term_no")
	doc.remarks = kwargs.get("remarks")
	if entry_type in ("Discount Given", "Co-pay Shared"):
		doc.margin_cost = abs(flt(amount)) * margin_factor(doc.benefit_category) / 100.0
	else:
		doc.margin_cost = 0
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def _term_no(card, date):
	rows = frappe.get_all("Care Card Term",
		filters={"parent": card, "parenttype": "Care Card"},
		fields=["term_no", "from_date", "to_date"])
	for row in rows:
		if row.from_date and row.to_date and getdate(row.from_date) <= getdate(date) <= getdate(row.to_date):
			return row.term_no
	return None


def post_usage(usage):
	"""One ledger entry per category per usage document."""
	by_category = {}
	for row in usage.lines or []:
		key = row.benefit_category or "Uncategorised"
		bucket = by_category.setdefault(key, {"discount": 0.0, "copay": 0.0})
		bucket["discount"] += flt(row.discount_amount)
		bucket["copay"] += flt(row.copay_shared)

	term_no = _term_no(usage.card, usage.posting_date)
	for category, bucket in by_category.items():
		cat = None if category == "Uncategorised" else category
		if bucket["discount"]:
			make_entry(usage.card, "Discount Given", -abs(bucket["discount"]),
				posting_date=usage.posting_date, tier=usage.tier,
				beneficiary_code=usage.beneficiary_code, benefit_category=cat,
				reference_doctype=usage.doctype, reference_name=usage.name,
				location=usage.location, term_no=term_no)
		if bucket["copay"]:
			make_entry(usage.card, "Co-pay Shared", -abs(bucket["copay"]),
				posting_date=usage.posting_date, tier=usage.tier,
				beneficiary_code=usage.beneficiary_code, benefit_category=cat,
				reference_doctype=usage.doctype, reference_name=usage.name,
				location=usage.location, term_no=term_no)


def reverse_usage(usage):
	reverse_reference(usage.doctype, usage.name, remarks=_("Usage cancelled"))


def post_fee(card, amount, term_no=None, reference_doctype=None, reference_name=None,
		posting_date=None, remarks=None):
	return make_entry(card, "Fee Collected", abs(flt(amount)), term_no=term_no,
		reference_doctype=reference_doctype, reference_name=reference_name,
		posting_date=posting_date, remarks=remarks)


def post_adjustment(adjustment):
	entry_type = "Refund" if adjustment.adjustment_type == "Fee Refund" else "Adjustment"
	amount = flt(adjustment.amount)
	if entry_type == "Adjustment":
		amount = -abs(amount) if amount > 0 else abs(amount)
	else:
		amount = -abs(amount)
	return make_entry(adjustment.card, entry_type, amount,
		posting_date=adjustment.posting_date,
		benefit_category=adjustment.benefit_category,
		reference_doctype=adjustment.doctype, reference_name=adjustment.name,
		remarks=adjustment.reason)


def reverse_reference(reference_doctype, reference_name, remarks=None):
	"""Mirror every live entry for a reference and mark the originals cancelled."""
	entries = frappe.get_all("Care Card Ledger Entry",
		filters={"reference_doctype": reference_doctype, "reference_name": reference_name,
			"is_cancelled": 0},
		fields=["name"])
	for row in entries:
		original = frappe.get_doc("Care Card Ledger Entry", row.name)
		reversal = make_entry(original.card, "Reversal", -flt(original.amount),
			posting_date=nowdate(), tier=original.tier,
			beneficiary_code=original.beneficiary_code,
			benefit_category=original.benefit_category,
			reference_doctype=reference_doctype, reference_name=reference_name,
			location=original.location, term_no=original.term_no,
			remarks=remarks or _("Reversal"))
		original.flags.ignore_immutable = True
		original.db_set("is_cancelled", 1, update_modified=False)
		original.db_set("cancelled_by_entry", reversal.name, update_modified=False)
		reversal.flags.ignore_immutable = True
		reversal.db_set("is_cancelled", 1, update_modified=False)


def balances(card, from_date=None, to_date=None):
	"""Aggregate the ledger for a card. Returns a dict of positive magnitudes."""
	filters = {"card": card, "is_cancelled": 0}
	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]
	rows = frappe.get_all("Care Card Ledger Entry", filters=filters,
		fields=["entry_type", "sum(amount) as amount", "sum(margin_cost) as margin_cost"],
		group_by="entry_type")
	out = {"fees": 0.0, "discount": 0.0, "copay": 0.0, "adjustment": 0.0,
		"refund": 0.0, "economic_cost": 0.0}
	for row in rows:
		amount = flt(row.amount)
		out["economic_cost"] += flt(row.margin_cost)
		if row.entry_type == "Fee Collected":
			out["fees"] += amount
		elif row.entry_type == "Discount Given":
			out["discount"] += abs(amount)
		elif row.entry_type == "Co-pay Shared":
			out["copay"] += abs(amount)
		elif row.entry_type == "Adjustment":
			out["adjustment"] += abs(amount)
		elif row.entry_type == "Refund":
			out["refund"] += abs(amount)
	out["total_benefit"] = out["discount"] + out["copay"] + out["adjustment"]
	out["contribution"] = out["fees"] - out["economic_cost"] - out["refund"]
	return out
