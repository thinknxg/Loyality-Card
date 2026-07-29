# Copyright (c) 2026, Kreatao and contributors
"""Template rendering and the outbound message queue (WhatsApp first)."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, now_datetime, nowdate


def get_template(event, language=None, channel="WhatsApp"):
	language = language or frappe.db.get_single_value("Care Card Settings", "default_language") or "en"
	name = frappe.db.get_value("Care Card Message Template",
		{"event": event, "language": language, "channel": channel, "is_active": 1}, "name")
	if not name:
		name = frappe.db.get_value("Care Card Message Template",
			{"event": event, "channel": channel, "is_active": 1}, "name")
	return frappe.get_cached_doc("Care Card Message Template", name) if name else None


def build_context(card, extra=None):
	context = {
		"card": card,
		"member_name": card.member_name,
		"tier": card.tier,
		"card_number": card.card_number,
		"expiry_date": card.expiry_date,
		"days_left": date_diff(card.expiry_date, nowdate()) if card.expiry_date else "",
		"card_url": frappe.utils.get_url("/my-card?card=%s" % card.card_number),
	}
	context.update(extra or {})
	return context


def queue_event(card, event, extra=None, channel="WhatsApp"):
	"""Render a template and drop it on the queue. Never raises."""
	try:
		if isinstance(card, str):
			card = frappe.get_doc("Care Card", card)
		if channel == "WhatsApp" and not card.whatsapp_consent:
			return _log(card, event, channel, status="Skipped",
				error=_("No WhatsApp consent on record"))
		template = get_template(event, card.preferred_language, channel)
		if not template:
			return _log(card, event, channel, status="Skipped",
				error=_("No active template for {0}").format(event))
		context = build_context(card, extra)
		message = frappe.render_template(template.message, context)
		subject = frappe.render_template(template.subject or "", context)
		attachment = None
		if template.attach_card_image:
			attachment = frappe.db.get_value("Care Card Digital Asset",
				{"card": card.name, "is_current": 1}, "card_file")
		return _log(card, event, channel, status="Queued", template=template.name,
			message=message, subject=subject, attachment=attachment,
			language=template.language,
			payload=json.dumps({k: str(v) for k, v in context.items() if k != "card"}))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Care Card: queue_event failed")
		return None


def _log(card, event, channel, **kwargs):
	log = frappe.new_doc("Care Card Message Log")
	log.card = card.name if hasattr(card, "name") else card
	log.event = event
	log.channel = channel
	log.to_number = card.mobile_whatsapp if hasattr(card, "mobile_whatsapp") else None
	for key, value in kwargs.items():
		setattr(log, key, value)
	log.flags.ignore_permissions = True
	log.insert(ignore_permissions=True)
	return log.name


def send(log_name):
	"""Dispatch one queued message through the configured provider."""
	from care_card.integrations.whatsapp import dispatch

	log = frappe.get_doc("Care Card Message Log", log_name)
	if log.status not in ("Queued", "Failed"):
		return
	limit = frappe.db.get_single_value("Care Card Settings", "message_retry_limit") or 3
	if (log.retry_count or 0) >= limit:
		return
	try:
		result = dispatch(log)
		log.db_set({
			"status": result.get("status", "Sent"),
			"provider": result.get("provider"),
			"provider_message_id": result.get("message_id"),
			"response": json.dumps(result.get("response") or {})[:14000],
			"sent_on": now_datetime(),
			"error": None,
		}, update_modified=False)
	except Exception as exc:
		log.db_set({
			"status": "Failed",
			"retry_count": (log.retry_count or 0) + 1,
			"error": str(exc)[:500],
		}, update_modified=False)
		frappe.log_error(frappe.get_traceback(), "Care Card: message dispatch failed")
