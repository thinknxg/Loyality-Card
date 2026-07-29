# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime
from frappe.model.document import Document

from care_card.utils.card_number import generate_card_number


class CareCard(Document):
	def before_insert(self):
		if not self.card_number:
			self.card_number = generate_card_number()
		if not self.issued_by:
			self.issued_by = frappe.session.user

	def validate(self):
		self.set_beneficiary_codes()
		self.validate_dependent_limit()
		self.sync_term_dates()
		if (self.whatsapp_consent or self.marketing_consent) and not self.consent_timestamp:
			self.consent_timestamp = now_datetime()

	def set_beneficiary_codes(self):
		seq = 0
		for row in self.dependents or []:
			seq += 1
			if not row.beneficiary_code:
				row.beneficiary_code = "%s-%02d" % (self.card_number or self.name, seq)
			if not row.added_on:
				row.added_on = nowdate()
			if not row.is_active and not row.removed_on:
				row.removed_on = nowdate()

	def validate_dependent_limit(self):
		if not self.tier:
			return
		limit = frappe.db.get_value("Care Card Tier", self.tier, "max_dependents") or 0
		active = len([d for d in (self.dependents or []) if d.is_active])
		if limit and active > limit:
			frappe.throw(_("Tier {0} covers at most {1} family members").format(self.tier, limit))

	def sync_term_dates(self):
		terms = sorted(self.terms or [], key=lambda r: (r.from_date or ""))
		for i, row in enumerate(terms, start=1):
			row.term_no = i
		paid = [r for r in terms if r.payment_status in ("Paid", "Waived")]
		if paid:
			self.activation_date = min(r.from_date for r in paid)
			self.expiry_date = max(r.to_date for r in paid)

	@frappe.whitelist()
	def activate(self, payment_status="Paid"):
		from care_card.membership import activate_card
		return activate_card(self, payment_status=payment_status)

	@frappe.whitelist()
	def renew(self, tier=None, fee_amount=None, payment_status="Paid"):
		from care_card.membership import renew_card
		return renew_card(self, tier=tier, fee_amount=fee_amount, payment_status=payment_status)

	@frappe.whitelist()
	def send_digital_card(self):
		from care_card.membership import issue_digital_card
		return issue_digital_card(self)

	@frappe.whitelist()
	def refresh_analytics(self):
		from care_card.analytics import refresh_card
		return refresh_card(self.name)

	def is_valid_on(self, date=None):
		date = date or nowdate()
		if self.status != "Active":
			return False
		for row in self.terms or []:
			if row.payment_status in ("Paid", "Waived") and row.from_date <= date <= row.to_date:
				return True
		return False

	def current_term(self, date=None):
		date = date or nowdate()
		for row in self.terms or []:
			if row.from_date and row.to_date and row.from_date <= date <= row.to_date:
				return row
		return None

