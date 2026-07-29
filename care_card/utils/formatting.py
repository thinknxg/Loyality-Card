# Copyright (c) 2026, Kreatao and contributors
import frappe
from frappe.utils import flt, formatdate


def fmt_currency(value, currency="OMR"):
	return "%s %s" % (currency, frappe.utils.fmt_money(flt(value), precision=3, currency=None))


def fmt_date(value):
	if not value:
		return ""
	return formatdate(value, "dd MMM yyyy")


def mask_civil_id(value):
	value = str(value or "")
	if len(value) <= 4:
		return value
	return "*" * (len(value) - 4) + value[-4:]
