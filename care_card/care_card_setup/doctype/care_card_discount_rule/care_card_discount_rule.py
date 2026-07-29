# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardDiscountRule(Document):
	def validate(self):
		if (self.discount_percent or 0) > 100:
			frappe.throw(_("Discount % cannot exceed 100"))
		if self.valid_from and self.valid_upto and self.valid_from > self.valid_upto:
			frappe.throw(_("Valid Upto cannot be before Valid From"))
		if not (self.item_code or self.brand or self.item_group or self.supplier):
			frappe.msgprint(_("No scope set — this rule becomes the category default for the tier."),
				indicator="orange", alert=True)
		frappe.cache().delete_value("care_card_discount_rules")

	def on_trash(self):
		frappe.cache().delete_value("care_card_discount_rules")

