# Copyright (c) 2026, Kreatao and contributors
"""Member facing endpoints backing /my-card and /care-card."""

import frappe
from frappe import _
from frappe.utils import flt

from care_card.analytics import card_summary


def _my_cards():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in"), frappe.PermissionError)
	names = frappe.get_all("Care Card", filters={"member_user": user}, pluck="name")
	if not names:
		email = frappe.db.get_value("User", user, "email")
		names = frappe.get_all("Care Card", filters={"email": email}, pluck="name") if email else []
	return names


@frappe.whitelist()
def my_card(card=None):
	names = _my_cards()
	if not names:
		return {"found": False}
	name = card if card in names else names[0]
	data = card_summary(name)
	doc = frappe.get_doc("Care Card", name)
	asset = frappe.db.get_value("Care Card Digital Asset",
		{"card": name, "beneficiary_code": doc.card_number, "is_current": 1},
		["card_svg", "qr_token", "card_url"], as_dict=True)
	return {
		"found": True,
		"cards": names,
		"card": {
			"name": doc.name,
			"card_number": doc.card_number,
			"member_name": doc.member_name,
			"tier": doc.tier,
			"status": doc.status,
			"activation_date": doc.activation_date,
			"expiry_date": doc.expiry_date,
			"dependents": [
				{"code": d.beneficiary_code, "name": d.dependent_name,
					"relationship": d.relationship, "is_active": d.is_active}
				for d in doc.dependents or []
			],
		},
		"asset": asset or {},
		"balances": data["balances"],
		"usage": data["usage"],
		"by_category": data["by_category"],
		"breakeven_percent": data["breakeven_percent"],
	}


@frappe.whitelist()
def add_dependent(card, dependent_name, relationship, date_of_birth=None, civil_id=None,
		mobile=None):
	names = _my_cards()
	if card not in names:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	doc = frappe.get_doc("Care Card", card)
	doc.append("dependents", {
		"dependent_name": dependent_name,
		"relationship": relationship,
		"date_of_birth": date_of_birth,
		"civil_id": civil_id,
		"mobile": mobile,
		"is_active": 1,
	})
	doc.save(ignore_permissions=True)

	from care_card.membership import issue_digital_card
	from care_card.messaging import queue_event

	issue_digital_card(doc)
	queue_event(doc, "Dependent Added", extra={"dependent_name": dependent_name})
	return True


@frappe.whitelist()
def tiers(program=None):
	"""Public tier comparison for the purchase page."""
	program = program or frappe.db.get_single_value("Care Card Settings", "default_program")
	out = []
	for name in frappe.get_all("Care Card Tier",
			filters={"is_active": 1, "program": program},
			order_by="sort_order asc", pluck="name"):
		doc = frappe.get_cached_doc("Care Card Tier", name)
		out.append({
			"name": doc.name,
			"annual_fee": flt(doc.annual_fee),
			"tagline": doc.tagline,
			"max_dependents": doc.max_dependents,
			"colour": doc.card_colour,
			"benefits": [
				{"category": b.benefit_category, "percent": flt(b.discount_percent)}
				for b in doc.benefits or [] if b.is_active
			],
		})
	return out


@frappe.whitelist(allow_guest=True)
def submit_application(applicant_name, mobile_whatsapp, tier, email=None, civil_id=None,
		date_of_birth=None, gender=None, city=None, dependents=None, program=None,
		terms_accepted=0, whatsapp_consent=0, marketing_consent=0):
	"""Public registration. Creates an application only — never a paid card."""
	if not int(terms_accepted or 0):
		frappe.throw(_("The terms and conditions must be accepted"))
	if isinstance(dependents, str):
		dependents = frappe.parse_json(dependents)
	program = program or frappe.db.get_single_value("Care Card Settings", "default_program")

	doc = frappe.new_doc("Care Card Application")
	doc.applicant_name = applicant_name
	doc.mobile_whatsapp = mobile_whatsapp
	doc.email = email
	doc.civil_id = civil_id
	doc.date_of_birth = date_of_birth
	doc.gender = gender
	doc.city = city
	doc.tier = tier
	doc.program = program
	doc.status = "Submitted"
	doc.source_channel = "Online Portal"
	doc.terms_accepted = 1
	doc.whatsapp_consent = 1 if int(whatsapp_consent or 0) else 0
	doc.marketing_consent = 1 if int(marketing_consent or 0) else 0
	for row in dependents or []:
		doc.append("dependents", {
			"dependent_name": row.get("dependent_name"),
			"relationship": row.get("relationship") or "Other",
			"date_of_birth": row.get("date_of_birth"),
			"civil_id": row.get("civil_id"),
			"mobile": row.get("mobile"),
		})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"application": doc.name, "fee_amount": flt(doc.fee_amount)}
