# Copyright (c) 2026, Kreatao and contributors
"""Card lifecycle: application to card, activation, renewal, digital issuance."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, nowdate

from care_card import ledger


# ------------------------------------------------------------------ creation
def create_card_from_application(application):
	if isinstance(application, str):
		application = frappe.get_doc("Care Card Application", application)
	if application.care_card:
		return application.care_card

	card = frappe.new_doc("Care Card")
	card.member_name = application.applicant_name
	card.program = application.program
	card.tier = application.tier
	card.mobile_whatsapp = application.mobile_whatsapp
	card.email = application.email
	card.civil_id = application.civil_id
	card.date_of_birth = application.date_of_birth
	card.gender = application.gender
	card.nationality = application.nationality
	card.address_line = application.address_line
	card.city = application.city
	card.region = application.region
	card.source_channel = application.source_channel
	card.sold_at_location = application.sold_at_location
	card.application = application.name
	card.whatsapp_consent = application.whatsapp_consent
	card.marketing_consent = application.marketing_consent
	card.consent_timestamp = application.consent_timestamp
	card.status = "Pending Payment"
	for row in application.dependents or []:
		card.append("dependents", {
			"dependent_name": row.dependent_name,
			"relationship": row.relationship,
			"date_of_birth": row.date_of_birth,
			"gender": row.gender,
			"civil_id": row.civil_id,
			"mobile": row.mobile,
			"is_active": 1,
		})
	card.flags.ignore_permissions = True
	card.insert(ignore_permissions=True)

	application.db_set("care_card", card.name)
	if application.status != "Converted":
		application.db_set("status", "Converted")

	if application.status == "Paid" or application.payment_reference:
		activate_card(card, payment_status="Paid",
			payment_method=application.payment_method,
			payment_reference=application.payment_reference)
	return card.name


# ---------------------------------------------------------------- activation
def _term_window(card, start=None):
	program = frappe.get_cached_doc("Care Card Program", card.program)
	start = getdate(start or nowdate())
	months = int(program.validity_months or 12)
	return start, add_days(add_months(start, months), -1)


def add_term(card, tier=None, from_date=None, fee_amount=None, payment_status="Unpaid",
		payment_method=None, payment_reference=None, sales_invoice=None):
	tier = tier or card.tier
	start, end = _term_window(card, from_date)
	if fee_amount is None:
		fee_amount = flt(frappe.db.get_value("Care Card Tier", tier, "annual_fee"))
	row = card.append("terms", {
		"tier": tier,
		"from_date": start,
		"to_date": end,
		"fee_amount": fee_amount,
		"payment_status": payment_status,
		"payment_method": payment_method,
		"payment_reference": payment_reference,
		"sales_invoice": sales_invoice,
	})
	return row


def activate_card(card, payment_status="Paid", payment_method=None, payment_reference=None,
		sales_invoice=None, from_date=None):
	if isinstance(card, str):
		card = frappe.get_doc("Care Card", card)

	open_term = None
	for row in card.terms or []:
		if row.payment_status not in ("Paid", "Waived"):
			open_term = row
			break
	if not open_term:
		open_term = add_term(card, from_date=from_date, payment_status="Unpaid")

	open_term.payment_status = payment_status
	open_term.payment_method = payment_method or open_term.payment_method
	open_term.payment_reference = payment_reference or open_term.payment_reference
	open_term.sales_invoice = sales_invoice or open_term.sales_invoice
	open_term.activated_on = now_datetime()

	card.status = "Active"
	card.flags.ignore_permissions = True
	card.save(ignore_permissions=True)

	if payment_status in ("Paid", "Waived") and flt(open_term.fee_amount):
		already = frappe.db.exists("Care Card Ledger Entry", {
			"card": card.name, "entry_type": "Fee Collected",
			"term_no": open_term.term_no, "is_cancelled": 0})
		if not already:
			ledger.post_fee(card.name, open_term.fee_amount, term_no=open_term.term_no,
				reference_doctype="Care Card", reference_name=card.name,
				posting_date=open_term.from_date,
				remarks=_("Annual subscription fee, term {0}").format(open_term.term_no))

	issue_digital_card(card)
	from care_card.messaging import queue_event

	queue_event(card, "Card Activation")
	from care_card.analytics import refresh_card

	refresh_card(card.name)
	return card.name


def renew_card(card, tier=None, fee_amount=None, payment_status="Paid",
		payment_method=None, payment_reference=None, sales_invoice=None):
	if isinstance(card, str):
		card = frappe.get_doc("Care Card", card)
	last_end = None
	for row in card.terms or []:
		if row.payment_status in ("Paid", "Waived") and row.to_date:
			last_end = max(last_end, getdate(row.to_date)) if last_end else getdate(row.to_date)
	start = add_days(last_end, 1) if last_end and last_end >= getdate(nowdate()) else nowdate()

	row = add_term(card, tier=tier, from_date=start, fee_amount=fee_amount,
		payment_status=payment_status, payment_method=payment_method,
		payment_reference=payment_reference, sales_invoice=sales_invoice)
	row.activated_on = now_datetime()
	if tier:
		card.tier = tier
	card.status = "Active"
	card.flags.ignore_permissions = True
	card.save(ignore_permissions=True)

	if payment_status in ("Paid", "Waived") and flt(row.fee_amount):
		ledger.post_fee(card.name, row.fee_amount, term_no=row.term_no,
			reference_doctype="Care Card", reference_name=card.name,
			posting_date=row.from_date,
			remarks=_("Renewal fee, term {0}").format(row.term_no))

	if frappe.db.get_single_value("Care Card Settings", "qr_rotate_on_renewal"):
		issue_digital_card(card)
	from care_card.messaging import queue_event

	queue_event(card, "Renewal Confirmed")
	from care_card.analytics import refresh_card

	refresh_card(card.name)
	return card.name


def mark_term_paid_by_invoice(invoice):
	row = frappe.db.get_value("Care Card Term", {"sales_invoice": invoice},
		["name", "parent", "term_no"], as_dict=True)
	if not row:
		return
	card = frappe.get_doc("Care Card", row.parent)
	for term in card.terms:
		if term.name == row.name and term.payment_status != "Paid":
			term.payment_status = "Paid"
			term.activated_on = now_datetime()
			card.status = "Active"
			card.flags.ignore_permissions = True
			card.save(ignore_permissions=True)
			ledger.post_fee(card.name, term.fee_amount, term_no=term.term_no,
				reference_doctype="Sales Invoice", reference_name=invoice,
				posting_date=term.from_date, remarks=_("Fee settled"))
			issue_digital_card(card)
			break


# ----------------------------------------------------------- digital issuance
def issue_digital_card(card, beneficiary_code=None):
	if isinstance(card, str):
		card = frappe.get_doc("Care Card", card)
	from care_card.utils.card_image import card_url, render_card_svg
	from care_card.utils.qr import make_token

	targets = [(None, card.card_number)]
	for dep in card.dependents or []:
		if dep.is_active:
			targets.append((dep, dep.beneficiary_code))

	if beneficiary_code:
		targets = [t for t in targets if t[1] == beneficiary_code]

	issued = []
	for beneficiary, code in targets:
		frappe.db.set_value("Care Card Digital Asset",
			{"card": card.name, "beneficiary_code": code, "is_current": 1},
			"is_current", 0, update_modified=False)
		token = make_token(card.card_number, code, card.expiry_date)
		asset = frappe.new_doc("Care Card Digital Asset")
		asset.card = card.name
		asset.beneficiary_code = code
		asset.asset_type = "Digital Card"
		asset.generated_on = now_datetime()
		asset.valid_upto = card.expiry_date
		asset.is_current = 1
		asset.qr_token = token
		asset.card_url = card_url(card)
		asset.card_svg = render_card_svg(card, beneficiary, token)
		asset.flags.ignore_permissions = True
		asset.insert(ignore_permissions=True)
		issued.append(asset.name)
	return issued


# ---------------------------------------------------------------- usage entry
def record_usage_from_billing(doc):
	"""Create a Care Card Usage from a submitted Sales/POS Invoice."""
	key = "%s:%s" % (doc.doctype, doc.name)
	if frappe.db.exists("Care Card Usage", {"idempotency_key": key, "docstatus": 1}):
		return
	usage = frappe.new_doc("Care Card Usage")
	usage.card = doc.get("care_card")
	usage.beneficiary_code = doc.get("care_card_beneficiary")
	usage.beneficiary_name = doc.get("care_card_beneficiary_name")
	usage.posting_datetime = now_datetime()
	usage.location = doc.get("care_card_location")
	usage.source_doctype = doc.doctype
	usage.source_docname = doc.name
	usage.idempotency_key = key
	usage.channel = "POS" if doc.doctype == "POS Invoice" else "Desk"
	usage.insurance_company = doc.get("cc_insurance_company")
	usage.insurance_plan = doc.get("cc_insurance_plan")
	usage.insurance_involved = 1 if doc.get("cc_insurance_company") else 0
	for row in doc.get("items") or []:
		if not (flt(row.get("cc_discount_amount")) or flt(row.get("cc_copay_shared"))):
			continue
		usage.append("lines", {
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"benefit_category": row.get("cc_benefit_category"),
			"qty": flt(row.get("qty")),
			"rate": flt(row.get("price_list_rate") or row.get("rate")),
			"gross_amount": flt(row.get("qty")) * flt(row.get("price_list_rate") or row.get("rate")),
			"discount_amount": flt(row.get("cc_discount_amount")),
			"copay_shared": flt(row.get("cc_copay_shared")),
			"is_insured": 1 if row.get("cc_is_insured") else 0,
			"rule_applied": row.get("cc_rule_applied"),
			"explanation": row.get("cc_explanation"),
		})
	if not usage.lines:
		return
	usage.flags.ignore_permissions = True
	usage.insert(ignore_permissions=True)
	usage.submit()
	return usage.name


def create_usage(card, lines, beneficiary_code=None, **kwargs):
	"""Create and submit a usage document from an already priced basket."""
	usage = frappe.new_doc("Care Card Usage")
	usage.card = card
	usage.beneficiary_code = beneficiary_code
	usage.beneficiary_name = kwargs.get("beneficiary_name")
	usage.posting_datetime = kwargs.get("posting_datetime") or now_datetime()
	usage.location = kwargs.get("location")
	usage.source_doctype = kwargs.get("source_doctype")
	usage.source_docname = kwargs.get("source_docname")
	usage.external_reference = kwargs.get("external_reference")
	usage.idempotency_key = kwargs.get("idempotency_key")
	usage.channel = kwargs.get("channel") or "Desk"
	usage.insurance_company = kwargs.get("insurance_company")
	usage.insurance_plan = kwargs.get("insurance_plan")
	usage.claim_reference = kwargs.get("claim_reference")
	usage.insurance_involved = 1 if kwargs.get("insurance_company") else 0
	usage.remarks = kwargs.get("remarks")
	for row in lines or []:
		if not (flt(row.get("discount_amount")) or flt(row.get("copay_shared"))):
			continue
		usage.append("lines", {
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"benefit_category": row.get("benefit_category"),
			"qty": flt(row.get("qty") or 1),
			"rate": flt(row.get("rate")),
			"gross_amount": flt(row.get("gross_amount") or row.get("amount")),
			"discount_percent": flt(row.get("discount_percent")),
			"discount_amount": flt(row.get("discount_amount")),
			"copay_shared": flt(row.get("copay_shared")),
			"is_insured": 1 if row.get("is_insured") else 0,
			"net_amount": flt(row.get("net_amount")),
			"rule_applied": row.get("rule_applied"),
			"explanation": row.get("explanation"),
		})
	if not usage.lines:
		return None
	usage.flags.ignore_permissions = True
	usage.insert(ignore_permissions=True)
	usage.submit()
	return usage
