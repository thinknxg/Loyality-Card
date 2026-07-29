# Copyright (c) 2026, Kreatao and contributors
"""KareXpert HIMS adapter.

KareXpert's outbound API is gated, so the integration is inbound first: the
HIS calls our signed endpoints and we translate its payload shape into the
engine's basket format. Field names live here and nowhere else, so a change
on their side is a one file change on ours.
"""

import frappe
from frappe.utils import flt

FIELD_MAP = {
	"item_code": ["serviceCode", "itemCode", "sku", "code"],
	"item_name": ["serviceName", "itemName", "description", "name"],
	"item_group": ["serviceGroup", "itemGroup", "category"],
	"brand": ["brand", "manufacturer"],
	"qty": ["quantity", "qty", "units"],
	"rate": ["unitPrice", "rate", "price"],
	"amount": ["netAmount", "amount", "grossAmount", "total"],
	"service_type": ["serviceType", "type"],
	"department": ["department", "departmentCode"],
	"is_insured": ["isInsured", "insuranceApplicable", "covered"],
	"copay_percent": ["copayPercent", "coPaymentPercent"],
	"copay_amount": ["copayAmount", "coPaymentAmount"],
	"existing_discount_percent": ["discountPercent", "existingDiscount"],
}


def _pick(row, keys):
	for key in keys:
		if key in row and row[key] not in (None, ""):
			return row[key]
	return None


def normalise_lines(raw_lines):
	"""Translate an HIS bill payload into the engine's line format."""
	lines = []
	for row in raw_lines or []:
		if not isinstance(row, dict):
			continue
		line = {}
		for target, sources in FIELD_MAP.items():
			value = _pick(row, sources)
			if value is not None:
				line[target] = value
		line["qty"] = flt(line.get("qty") or 1)
		line["rate"] = flt(line.get("rate"))
		if not line.get("amount"):
			line["amount"] = line["qty"] * line["rate"]
		line["is_insured"] = 1 if str(line.get("is_insured")).lower() in ("1", "true", "yes") else 0
		lines.append(line)
	return lines


def normalise_context(payload):
	return {
		"posting_date": payload.get("billDate") or payload.get("posting_date"),
		"location": payload.get("location"),
		"location_hint": {"external_code": payload.get("locationCode")
			or payload.get("facilityCode")},
	}


def resolve_beneficiary(payload):
	"""Map an HIS patient identifier to a card beneficiary code."""
	code = payload.get("beneficiaryCode") or payload.get("beneficiary_code")
	if code:
		return code
	patient_id = payload.get("patientId") or payload.get("mrn")
	if not patient_id:
		return None
	card = frappe.db.get_value("Care Card", {"external_patient_id": patient_id}, "card_number")
	if card:
		return card
	return frappe.db.get_value("Care Card Dependent",
		{"external_patient_id": patient_id}, "beneficiary_code")
