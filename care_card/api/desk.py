# Copyright (c) 2026, Kreatao and contributors
"""Counter and pharmacy staff endpoints backing /card-desk."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from care_card.engine.pricing import card_eligibility, get_card, resolve_basket
from care_card.permissions import CASHIER_ROLES, FULL_ACCESS_ROLES

ALLOWED = FULL_ACCESS_ROLES | CASHIER_ROLES


def _guard(write=False):
	roles = set(frappe.get_roles())
	if frappe.session.user == "Guest" or not (ALLOWED & roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if write and not ({"System Manager", "Care Card Manager", "Care Card Sales Agent",
			"Care Card Hospital Cashier", "Care Card Pharmacy Cashier"} & roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def search(query=None):
	_guard()
	query = (query or "").strip()
	if not query:
		return []
	like = "%%%s%%" % query
	rows = frappe.db.sql("""
		select name, card_number, member_name, tier, status, mobile_whatsapp, expiry_date
		from `tabCare Card`
		where card_number like %(like)s or member_name like %(like)s
			or mobile_whatsapp like %(like)s or civil_id like %(like)s or name like %(like)s
		order by modified desc limit 20
	""", {"like": like}, as_dict=True)
	if not rows:
		parents = frappe.get_all("Care Card Dependent",
			filters=[["dependent_name", "like", like]], fields=["parent"], limit=20)
		names = list({p.parent for p in parents})
		if names:
			rows = frappe.get_all("Care Card", filters={"name": ["in", names]},
				fields=["name", "card_number", "member_name", "tier", "status",
					"mobile_whatsapp", "expiry_date"])
	return rows


@frappe.whitelist()
def card_detail(card):
	_guard()
	doc = get_card(card)
	if not doc:
		frappe.throw(_("Card not found"))
	elig = card_eligibility(doc)
	asset = frappe.db.get_value("Care Card Digital Asset",
		{"card": doc.name, "beneficiary_code": doc.card_number, "is_current": 1},
		["qr_token", "card_svg", "card_url"], as_dict=True)
	return {
		"name": doc.name,
		"card_number": doc.card_number,
		"member_name": doc.member_name,
		"tier": doc.tier,
		"status": doc.status,
		"mobile": doc.mobile_whatsapp,
		"activation_date": doc.activation_date,
		"expiry_date": doc.expiry_date,
		"eligible": elig["eligible"],
		"reason": elig.get("reason"),
		"beneficiaries": [{"code": doc.card_number, "name": doc.member_name,
			"relationship": "Self"}] + [
			{"code": d.beneficiary_code, "name": d.dependent_name,
				"relationship": d.relationship}
			for d in doc.dependents or [] if d.is_active],
		"utilization": {
			"fees": flt(doc.total_fees_paid),
			"benefit": flt(doc.total_benefit),
			"ratio": flt(doc.utilization_ratio),
			"breakeven_date": doc.breakeven_date,
			"visits": doc.visit_count,
		},
		"asset": asset or {},
	}


@frappe.whitelist()
def price_basket(card, lines, beneficiary_code=None, location=None):
	_guard()
	if isinstance(lines, str):
		lines = frappe.parse_json(lines)
	return resolve_basket(card, lines, beneficiary_code=beneficiary_code,
		context={"location": location, "posting_date": nowdate()})


@frappe.whitelist()
def record_usage(card, lines, beneficiary_code=None, location=None, reference=None,
		insurance_company=None, insurance_plan=None, remarks=None):
	"""Price and post a manual (non-ERPNext) bill in one call."""
	_guard(write=True)
	if isinstance(lines, str):
		lines = frappe.parse_json(lines)
	result = resolve_basket(card, lines, beneficiary_code=beneficiary_code,
		context={"location": location, "posting_date": nowdate()})
	if not result.get("eligible"):
		frappe.throw(result.get("reason") or _("Card not eligible"))

	from care_card.membership import create_usage

	usage = create_usage(result["card"], result["lines"],
		beneficiary_code=result.get("beneficiary_code"),
		beneficiary_name=result.get("beneficiary_name"),
		location=result.get("location") or location,
		external_reference=reference,
		idempotency_key=("DESK:%s" % reference) if reference else None,
		channel="Desk", insurance_company=insurance_company,
		insurance_plan=insurance_plan, remarks=remarks)
	return {"usage": usage.name if usage else None, "totals": result["totals"],
		"lines": result["lines"]}


@frappe.whitelist()
def sell_card(member_name, mobile_whatsapp, tier, program=None, dependents=None,
		civil_id=None, email=None, payment_method=None, payment_reference=None,
		location=None, source_channel="Hospital Counter", whatsapp_consent=1):
	_guard(write=True)
	program = program or frappe.db.get_single_value("Care Card Settings", "default_program")
	if isinstance(dependents, str):
		dependents = frappe.parse_json(dependents)

	card = frappe.new_doc("Care Card")
	card.member_name = member_name
	card.mobile_whatsapp = mobile_whatsapp
	card.civil_id = civil_id
	card.email = email
	card.tier = tier
	card.program = program
	card.sold_at_location = location
	card.source_channel = source_channel
	card.whatsapp_consent = 1 if int(whatsapp_consent or 0) else 0
	card.status = "Pending Payment"
	for row in dependents or []:
		card.append("dependents", {
			"dependent_name": row.get("dependent_name"),
			"relationship": row.get("relationship") or "Other",
			"date_of_birth": row.get("date_of_birth"),
			"civil_id": row.get("civil_id"),
			"mobile": row.get("mobile"),
			"is_active": 1,
		})
	card.insert(ignore_permissions=True)

	from care_card.membership import activate_card

	activate_card(card, payment_status="Paid", payment_method=payment_method,
		payment_reference=payment_reference)
	return {"card": card.name, "card_number": card.card_number}


@frappe.whitelist()
def resend_card(card):
	_guard(write=True)
	from care_card.membership import issue_digital_card
	from care_card.messaging import queue_event

	issue_digital_card(card)
	queue_event(card, "Card Activation")
	return True


@frappe.whitelist()
def renewal_queue(days=30):
	_guard()
	return frappe.db.sql("""
		select name, card_number, member_name, tier, mobile_whatsapp, expiry_date,
			total_fees_paid, total_benefit, utilization_ratio
		from `tabCare Card`
		where status = 'Active'
			and expiry_date between curdate() and date_add(curdate(), interval %s day)
		order by expiry_date asc
	""", int(days), as_dict=True)
