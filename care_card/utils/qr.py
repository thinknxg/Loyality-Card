# Copyright (c) 2026, Kreatao and contributors
"""Signed QR tokens so a pharmacy can validate a card without a round trip."""

import base64
import hashlib
import hmac
import json

import frappe
from frappe.utils import getdate, nowdate


def _secret() -> bytes:
	settings = frappe.get_single("Care Card Settings")
	secret = settings.get_password("qr_secret", raise_exception=False)
	if not secret:
		secret = frappe.generate_hash(length=48)
		settings.qr_secret = secret
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()
	return secret.encode("utf-8")


def _b64(raw: bytes) -> str:
	return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
	pad = "=" * (-len(text) % 4)
	return base64.urlsafe_b64decode(text + pad)


def make_token(card_number: str, beneficiary_code: str = None, valid_upto: str = None) -> str:
	payload = {
		"cn": card_number,
		"bc": beneficiary_code or card_number,
		"exp": str(valid_upto or ""),
		"v": 1,
	}
	body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
	sig = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())[:32]
	return body + "." + sig


def read_token(token: str) -> dict:
	"""Return the payload of a valid token, or raise."""
	try:
		body, sig = (token or "").split(".", 1)
	except ValueError:
		frappe.throw(frappe._("Malformed card token"))
	expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())[:32]
	if not hmac.compare_digest(sig, expected):
		frappe.throw(frappe._("Card token signature is not valid"))
	payload = json.loads(_unb64(body).decode("utf-8"))
	if payload.get("exp") and getdate(payload["exp"]) < getdate(nowdate()):
		payload["expired"] = True
	return payload
