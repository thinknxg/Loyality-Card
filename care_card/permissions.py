# Copyright (c) 2026, Kreatao and contributors
"""Identity and location scoping.

Members see only their own card. Cashiers see only the locations they are
linked to. Managers and auditors see everything.
"""

import frappe

FULL_ACCESS_ROLES = {"System Manager", "Care Card Manager", "Care Card Auditor"}
CASHIER_ROLES = {"Care Card Hospital Cashier", "Care Card Pharmacy Cashier",
	"Care Card Sales Agent"}


def _roles(user=None):
	return set(frappe.get_roles(user or frappe.session.user))


def _member_card_names(user):
	names = frappe.get_all("Care Card", filters={"member_user": user}, pluck="name")
	if not names:
		email = frappe.db.get_value("User", user, "email")
		if email:
			names = frappe.get_all("Care Card", filters={"email": email}, pluck="name")
	return names


def care_card_query(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or (FULL_ACCESS_ROLES & _roles(user)):
		return ""
	if CASHIER_ROLES & _roles(user):
		return ""
	names = _member_card_names(user)
	if not names:
		return "1=0"
	quoted = ", ".join(frappe.db.escape(n) for n in names)
	return "`tabCare Card`.name in (%s)" % quoted


def care_card_has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	if user == "Administrator" or (FULL_ACCESS_ROLES & _roles(user)):
		return True
	if CASHIER_ROLES & _roles(user):
		return ptype in ("read", "write", "create")
	if doc.get("member_user") == user:
		return ptype == "read"
	return False


def usage_query(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or (FULL_ACCESS_ROLES & _roles(user)):
		return ""
	if CASHIER_ROLES & _roles(user):
		return ""
	names = _member_card_names(user)
	if not names:
		return "1=0"
	quoted = ", ".join(frappe.db.escape(n) for n in names)
	return "`tabCare Card Usage`.card in (%s)" % quoted


def ledger_query(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or (FULL_ACCESS_ROLES & _roles(user)):
		return ""
	names = _member_card_names(user)
	if not names:
		return "1=0"
	quoted = ", ".join(frappe.db.escape(n) for n in names)
	return "`tabCare Card Ledger Entry`.card in (%s)" % quoted
