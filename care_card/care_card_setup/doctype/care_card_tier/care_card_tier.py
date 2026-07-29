# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardTier(Document):
	def validate(self):
		if self.annual_fee is not None and self.annual_fee < 0:
			frappe.throw(_("Annual Fee cannot be negative"))
		seen = set()
		for row in self.benefits or []:
			if row.benefit_category in seen:
				frappe.throw(_("Benefit Category {0} appears more than once").format(row.benefit_category))
			seen.add(row.benefit_category)
			if row.discount_type == "Percentage" and (row.discount_percent or 0) > 100:
				frappe.throw(_("Discount % cannot exceed 100 for {0}").format(row.benefit_category))
		frappe.cache().delete_value("care_card_tier_matrix")

	def on_trash(self):
		frappe.cache().delete_value("care_card_tier_matrix")

