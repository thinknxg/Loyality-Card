# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareBenefitCategory(Document):
	def validate(self):
		if self.margin_factor is None:
			self.margin_factor = 100
		if self.margin_factor < 0 or self.margin_factor > 100:
			frappe.throw(_("Margin Factor must be between 0 and 100"))
		frappe.cache().delete_value("care_card_categories")

	def on_trash(self):
		frappe.cache().delete_value("care_card_categories")

