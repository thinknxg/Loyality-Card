# Copyright (c) 2026, Kreatao and contributors
"""Binds the pricing engine into ERPNext billing documents.

Every hook is defensive: if ERPNext is absent, or the card field was never
added, nothing here does anything.
"""

import frappe
from frappe import _
from frappe.utils import flt

from care_card.engine.pricing import resolve_basket

BILLING_DOCTYPES = ("Sales Invoice", "POS Invoice")


def _enabled():
	try:
		return bool(frappe.db.get_single_value("Care Card Settings", "enabled"))
	except Exception:
		return False


def _line_payload(doc):
	lines = []
	for row in doc.get("items") or []:
		lines.append({
			"row_name": row.name,
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"item_group": row.get("item_group"),
			"brand": row.get("brand"),
			"qty": flt(row.get("qty")),
			"rate": flt(row.get("price_list_rate") or row.get("rate")),
			"amount": flt(row.get("qty")) * flt(row.get("price_list_rate") or row.get("rate")),
			"service_type": row.get("cc_service_type"),
			"department": row.get("cost_center"),
			"is_insured": 1 if row.get("cc_is_insured") else 0,
			"copay_percent": flt(row.get("cc_copay_percent")),
			"copay_amount": flt(row.get("cc_copay_amount")),
			"insurance_company": doc.get("cc_insurance_company"),
			"insurance_plan": doc.get("cc_insurance_plan"),
			"existing_discount_percent": flt(row.get("cc_existing_discount_percent")),
		})
	return lines


def before_validate(doc, method=None):
	if doc.doctype not in BILLING_DOCTYPES or not _enabled():
		return
	card = doc.get("care_card")
	if not card:
		for row in doc.get("items") or []:
			if row.get("cc_benefit_category"):
				row.cc_benefit_category = None
				row.cc_discount_amount = 0
		doc.care_card_discount_total = 0
		doc.care_card_copay_shared = 0
		return

	context = {
		"posting_date": doc.get("posting_date"),
		"location": doc.get("care_card_location"),
		"location_hint": {
			"branch": doc.get("branch"),
			"cost_center": doc.get("cost_center"),
			"warehouse": doc.get("set_warehouse"),
			"pos_profile": doc.get("pos_profile"),
		},
	}
	result = resolve_basket(card, _line_payload(doc),
		beneficiary_code=doc.get("care_card_beneficiary"), context=context)

	if not result.get("eligible"):
		doc.care_card_status = result.get("reason") or _("Not eligible")
		doc.care_card_discount_total = 0
		doc.care_card_copay_shared = 0
		if frappe.db.get_single_value("Care Card Settings", "block_expired_cards"):
			frappe.msgprint(_("Care Card {0}: {1}").format(card, result.get("reason")),
				indicator="orange", alert=True)
		return

	doc.care_card_status = _("Eligible")
	doc.care_card_tier = result.get("tier")
	by_row = {}
	for priced, source in zip(result["lines"], _line_payload(doc)):
		by_row[source["row_name"]] = priced

	for row in doc.get("items") or []:
		priced = by_row.get(row.name)
		if not priced:
			continue
		row.cc_benefit_category = priced.get("benefit_category")
		row.cc_discount_amount = priced.get("discount_amount")
		row.cc_copay_shared = priced.get("copay_shared")
		row.cc_rule_applied = priced.get("rule_applied")
		row.cc_explanation = priced.get("explanation")
		if flt(priced.get("discount_percent")):
			row.discount_percentage = flt(priced["discount_percent"])
			row.rate = flt(row.price_list_rate or row.rate) * (1 - row.discount_percentage / 100.0)

	doc.care_card_discount_total = result["totals"]["discount"]
	doc.care_card_copay_shared = result["totals"]["copay_shared"]
	doc.care_card_beneficiary_name = result.get("beneficiary_name")


def on_submit(doc, method=None):
	if doc.doctype not in BILLING_DOCTYPES or not _enabled():
		return
	if not doc.get("care_card"):
		return
	if not (flt(doc.get("care_card_discount_total")) or flt(doc.get("care_card_copay_shared"))):
		return
	from care_card.membership import record_usage_from_billing

	record_usage_from_billing(doc)


def on_cancel(doc, method=None):
	if doc.doctype not in BILLING_DOCTYPES:
		return
	names = frappe.get_all("Care Card Usage",
		filters={"source_doctype": doc.doctype, "source_docname": doc.name, "docstatus": 1},
		pluck="name")
	for name in names:
		usage = frappe.get_doc("Care Card Usage", name)
		usage.flags.ignore_permissions = True
		usage.cancel()


def payment_on_submit(doc, method=None):
	"""Mark a card term paid when its fee invoice is settled."""
	if doc.doctype != "Payment Entry":
		return
	invoices = [r.reference_name for r in doc.get("references") or []
		if r.reference_doctype == "Sales Invoice"]
	if not invoices:
		return
	from care_card.membership import mark_term_paid_by_invoice

	for invoice in invoices:
		mark_term_paid_by_invoice(invoice)
