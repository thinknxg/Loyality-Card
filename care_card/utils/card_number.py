# Copyright (c) 2026, Kreatao and contributors
"""Card number generation — 16 digits, Luhn check digit, barcode friendly."""

import random

import frappe


def luhn_check_digit(number: str) -> int:
	total = 0
	for i, ch in enumerate(reversed(number)):
		d = int(ch)
		if i % 2 == 0:
			d *= 2
			if d > 9:
				d -= 9
		total += d
	return (10 - (total % 10)) % 10


def is_valid_card_number(number: str) -> bool:
	number = (number or "").strip().replace(" ", "").replace("-", "")
	if not number.isdigit() or len(number) < 8:
		return False
	return luhn_check_digit(number[:-1]) == int(number[-1])


def generate_card_number(prefix: str = None) -> str:
	"""Return a unique 16 digit card number: prefix + random body + Luhn digit."""
	if prefix is None:
		prefix = frappe.db.get_single_value("Care Card Settings", "card_number_prefix") or "97"
	prefix = "".join(ch for ch in str(prefix) if ch.isdigit())[:4] or "97"
	body_len = 15 - len(prefix)
	for _ in range(40):
		body = "".join(str(random.randint(0, 9)) for _ in range(body_len))
		stem = prefix + body
		number = stem + str(luhn_check_digit(stem))
		if not frappe.db.exists("Care Card", {"card_number": number}):
			return number
	frappe.throw(frappe._("Could not allocate a unique card number. Try again."))


def normalise(number: str) -> str:
	return (number or "").strip().replace(" ", "").replace("-", "").upper()
