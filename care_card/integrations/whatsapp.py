# Copyright (c) 2026, Kreatao and contributors
"""Pluggable WhatsApp provider layer.

Providers are intentionally thin. Nothing outside this module knows which
vendor is in use, so swapping Meta Cloud API for an aggregator is a settings
change rather than a code change.
"""

import json

import frappe
from frappe import _


def _settings():
	return frappe.get_single("Care Card Settings")


def _post(url, payload, headers=None):
	import requests

	response = requests.post(url, json=payload, headers=headers or {}, timeout=20)
	body = {}
	try:
		body = response.json()
	except Exception:
		body = {"text": response.text[:2000]}
	if response.status_code >= 400:
		raise frappe.ValidationError("Provider error %s: %s" % (response.status_code, body))
	return body


def dispatch(log):
	settings = _settings()
	provider = settings.whatsapp_provider or "Disabled"
	to = (log.to_number or "").strip()
	if not to:
		raise frappe.ValidationError(_("No destination number"))

	if provider == "Disabled":
		return {"status": "Skipped", "provider": provider,
			"response": {"note": "WhatsApp provider not configured"}}

	token = settings.get_password("whatsapp_token", raise_exception=False)

	if provider == "Meta Cloud API":
		url = (settings.whatsapp_api_url
			or "https://graph.facebook.com/v19.0/%s/messages" % (settings.whatsapp_account_id or ""))
		template_name = frappe.db.get_value("Care Card Message Template", log.template,
			"whatsapp_template_name") if log.template else None
		if template_name:
			variables = _ordered_variables(log)
			payload = {
				"messaging_product": "whatsapp",
				"to": to,
				"type": "template",
				"template": {
					"name": template_name,
					"language": {"code": log.language or "en"},
					"components": [{
						"type": "body",
						"parameters": [{"type": "text", "text": v} for v in variables],
					}],
				},
			}
		else:
			payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
				"text": {"body": log.message or ""}}
		body = _post(url, payload, {"Authorization": "Bearer %s" % token})
		message_id = ((body.get("messages") or [{}])[0]).get("id")
		return {"status": "Sent", "provider": provider, "message_id": message_id,
			"response": body}

	if provider == "Twilio":
		url = settings.whatsapp_api_url or ""
		payload = {"To": "whatsapp:%s" % to,
			"From": "whatsapp:%s" % (settings.whatsapp_sender_id or ""),
			"Body": log.message or ""}
		body = _post(url, payload, {"Authorization": "Basic %s" % (token or "")})
		return {"status": "Sent", "provider": provider,
			"message_id": body.get("sid"), "response": body}

	if provider == "360dialog":
		url = settings.whatsapp_api_url or "https://waba.360dialog.io/v1/messages"
		payload = {"to": to, "type": "text", "text": {"body": log.message or ""}}
		body = _post(url, payload, {"D360-API-KEY": token or ""})
		return {"status": "Sent", "provider": provider,
			"message_id": ((body.get("messages") or [{}])[0]).get("id"), "response": body}

	if provider == "Custom Webhook":
		url = settings.custom_webhook_url
		if not url:
			raise frappe.ValidationError(_("Custom Webhook URL is not set"))
		payload = {
			"to": to, "event": log.event, "message": log.message,
			"subject": log.subject, "language": log.language,
			"card": log.card, "attachment": log.attachment,
			"context": json.loads(log.payload) if log.payload else {},
		}
		body = _post(url, payload, {"Authorization": "Bearer %s" % (token or "")})
		return {"status": "Sent", "provider": provider,
			"message_id": body.get("id"), "response": body}

	raise frappe.ValidationError(_("Unknown WhatsApp provider {0}").format(provider))


def _ordered_variables(log):
	order = frappe.db.get_value("Care Card Message Template", log.template,
		"variable_order") if log.template else None
	context = json.loads(log.payload) if log.payload else {}
	if order:
		return [str(context.get(key.strip(), "")) for key in order.split(",") if key.strip()]
	return [log.message or ""]


def poll_receipts():
	"""Placeholder for provider delivery receipt polling.

	Meta and 360dialog push receipts to a webhook; Twilio can be polled. Wire the
	site's webhook to ``care_card.api.external.delivery_receipt``.
	"""
	return True
