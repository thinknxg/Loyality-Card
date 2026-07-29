# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardInsuranceRule(Document):
	def validate(self):
		share = self.cardholder_share_percent or 0
		if share < 0 or share > 100:
			frappe.throw(_("Cardholder Share of Co-pay % must be between 0 and 100"))
		self.hospital_share_percent = 100 - share
		if self.valid_from and self.valid_upto and self.valid_from > self.valid_upto:
			frappe.throw(_("Valid Upto cannot be before Valid From"))
		frappe.cache().delete_value("care_card_insurance_rules")

	def on_trash(self):
		frappe.cache().delete_value("care_card_insurance_rules")

