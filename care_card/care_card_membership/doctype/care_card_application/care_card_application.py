# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class CareCardApplication(Document):
	def validate(self):
		if self.tier and not self.fee_amount:
			self.fee_amount = frappe.db.get_value("Care Card Tier", self.tier, "annual_fee")
		if (self.whatsapp_consent or self.marketing_consent) and not self.consent_timestamp:
			self.consent_timestamp = now_datetime()
		self.validate_dependent_limit()

	def validate_dependent_limit(self):
		if not self.tier:
			return
		limit = frappe.db.get_value("Care Card Tier", self.tier, "max_dependents") or 0
		if limit and len(self.dependents or []) > limit:
			frappe.throw(_("Tier {0} allows at most {1} dependents").format(self.tier, limit))

	@frappe.whitelist()
	def convert_to_card(self):
		from care_card.membership import create_card_from_application
		return create_card_from_application(self)

