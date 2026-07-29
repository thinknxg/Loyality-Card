# Copyright (c) 2026, Kreatao and contributors
"""Signed inbound API for a third-party HIS (KareXpert) or pharmacy POS.

Auth: ``X-CareCard-Signature: HMAC-SHA256(secret, "<timestamp>.<raw body>")``
hex encoded, with ``X-CareCard-Timestamp`` inside the configured window.

verify  -> card status, tier, beneficiaries, remaining caps
quote   -> price a basket, no side effects
commit  -> record a finalised bill (idempotent on ``reference``)
reverse -> reverse a committed bill
"""

import hashlib
import hmac
import json
import time

import frappe
from frappe import _

from care_card.engine.pricing import card_eligibility, get_card, resolve_basket
from care_card.integrations import karexpert


# ----------------------------------------------------------------- plumbing
def _settings():
	return frappe.get_cached_doc("Care Card Settings")


def _raw_body():
	try:
		return frappe.request.get_data(as_text=True) or ""
	except Exception:
		return ""


def _authenticate():
	settings = _settings()
	if not settings.enable_external_api:
		frappe.throw(_("The Care Card external API is disabled"), frappe.PermissionError)

	allowed = [ip.strip() for ip in (settings.allowed_ips or "").splitlines() if ip.strip()]
	if allowed:
		remote = frappe.local.request_ip
		if remote not in allowed:
			frappe.throw(_("Source address not allowed"), frappe.PermissionError)

	secret = settings.get_password("api_secret", raise_exception=False)
	if not secret:
		frappe.throw(_("No shared secret configured"), frappe.PermissionError)

	headers = frappe.request.headers if frappe.request else {}
	signature = headers.get("X-CareCard-Signature") or ""
	timestamp = headers.get("X-CareCard-Timestamp") or ""
	if not signature or not timestamp:
		frappe.throw(_("Missing signature headers"), frappe.PermissionError)

	tolerance = int(settings.api_timestamp_tolerance or 300)
	try:
		skew = abs(time.time() - float(timestamp))
	except ValueError:
		frappe.throw(_("Malformed timestamp"), frappe.PermissionError)
	if skew > tolerance:
		frappe.throw(_("Request timestamp outside the allowed window"), frappe.PermissionError)

	base = "%s.%s" % (timestamp, _raw_body())
	expected = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
	if not hmac.compare_digest(signature.strip().lower(), expected):
		frappe.throw(_("Signature mismatch"), frappe.PermissionError)
	return True


def _payload(**kwargs):
	body = _raw_body()
	if body:
		try:
			return json.loads(body)
		except ValueError:
			pass
	return kwargs or dict(frappe.local.form_dict or {})


def _ok(data):
	frappe.local.response["http_status_code"] = 200
	return {"ok": True, "data": data}


# ---------------------------------------------------------------- endpoints
@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify(**kwargs):
	_authenticate()
	payload = _payload(**kwargs)
	identifier = payload.get("card") or payload.get("cardNumber") or payload.get("token")
	card = get_card(identifier)
	if not card:
		return {"ok": False, "error": "Card not found"}

	elig = card_eligibility(card, payload.get("beneficiaryCode")
		or payload.get("beneficiary_code"))
	term = elig.get("term")
	return _ok({
		"card": card.name,
		"cardNumber": card.card_number,
		"memberName": card.member_name,
		"tier": card.tier,
		"status": card.status,
		"eligible": elig["eligible"],
		"reason": elig.get("reason"),
		"activationDate": str(card.activation_date or ""),
		"expiryDate": str(card.expiry_date or ""),
		"term": {"no": term.term_no, "from": str(term.from_date), "to": str(term.to_date)}
			if term else None,
		"beneficiaries": [
			{"code": card.card_number, "name": card.member_name, "relationship": "Self"}
		] + [
			{"code": d.beneficiary_code, "name": d.dependent_name,
				"relationship": d.relationship}
			for d in card.dependents or [] if d.is_active
		],
		"utilization": {
			"feesPaid": card.total_fees_paid,
			"benefitAvailed": card.total_benefit,
			"ratio": card.utilization_ratio,
			"breakevenDate": str(card.breakeven_date or ""),
		},
	})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def quote(**kwargs):
	_authenticate()
	payload = _payload(**kwargs)
	identifier = payload.get("card") or payload.get("cardNumber") or payload.get("token")
	lines = karexpert.normalise_lines(payload.get("lines") or payload.get("items"))
	if not lines:
		return {"ok": False, "error": "No lines supplied"}
	result = resolve_basket(identifier, lines,
		beneficiary_code=karexpert.resolve_beneficiary(payload),
		context=karexpert.normalise_context(payload))
	return _ok(result)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def commit(**kwargs):
	_authenticate()
	payload = _payload(**kwargs)
	reference = payload.get("reference") or payload.get("billNumber")
	if not reference:
		return {"ok": False, "error": "reference is required for idempotency"}

	key = "EXT:%s" % reference
	existing = frappe.db.get_value("Care Card Usage",
		{"idempotency_key": key, "docstatus": 1}, "name")
	if existing:
		return _ok({"usage": existing, "duplicate": True})

	identifier = payload.get("card") or payload.get("cardNumber") or payload.get("token")
	lines = karexpert.normalise_lines(payload.get("lines") or payload.get("items"))
	beneficiary = karexpert.resolve_beneficiary(payload)
	result = resolve_basket(identifier, lines, beneficiary_code=beneficiary,
		context=karexpert.normalise_context(payload))
	if not result.get("eligible"):
		return {"ok": False, "error": result.get("reason") or "Card not eligible"}

	from care_card.membership import create_usage

	usage = create_usage(
		result["card"], result["lines"], beneficiary_code=result.get("beneficiary_code"),
		beneficiary_name=result.get("beneficiary_name"), location=result.get("location"),
		external_reference=reference, idempotency_key=key, channel="External API",
		source_doctype=payload.get("sourceDoctype"), source_docname=payload.get("sourceDocname"),
		insurance_company=payload.get("insuranceCompany"),
		insurance_plan=payload.get("insurancePlan"),
		claim_reference=payload.get("claimReference"),
		remarks=payload.get("remarks"))
	frappe.db.commit()
	return _ok({
		"usage": usage.name if usage else None,
		"totals": result["totals"],
		"lines": result["lines"],
	})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def reverse(**kwargs):
	_authenticate()
	payload = _payload(**kwargs)
	reference = payload.get("reference") or payload.get("billNumber")
	name = frappe.db.get_value("Care Card Usage",
		{"idempotency_key": "EXT:%s" % reference, "docstatus": 1}, "name")
	if not name:
		return {"ok": False, "error": "No committed usage for that reference"}
	usage = frappe.get_doc("Care Card Usage", name)
	usage.flags.ignore_permissions = True
	usage.cancel()
	frappe.db.commit()
	return _ok({"usage": name, "status": "reversed"})


@frappe.whitelist(allow_guest=True, methods=["POST"])
def delivery_receipt(**kwargs):
	"""Provider webhook for WhatsApp delivery status."""
	_authenticate()
	payload = _payload(**kwargs)
	message_id = payload.get("messageId") or payload.get("id")
	status = (payload.get("status") or "").title()
	if not message_id:
		return {"ok": False, "error": "messageId is required"}
	name = frappe.db.get_value("Care Card Message Log",
		{"provider_message_id": message_id}, "name")
	if not name:
		return {"ok": False, "error": "Unknown message"}
	if status in ("Delivered", "Read", "Failed", "Sent"):
		frappe.db.set_value("Care Card Message Log", name, "status", status,
			update_modified=False)
		if status in ("Delivered", "Read"):
			frappe.db.set_value("Care Card Message Log", name, "delivered_on",
				frappe.utils.now_datetime(), update_modified=False)
	frappe.db.commit()
	return _ok({"message": name, "status": status})
