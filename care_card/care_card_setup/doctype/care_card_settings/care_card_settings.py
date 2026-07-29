# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardSettings(Document):
	def validate(self):
		if self.enable_external_api and not self.get_password("api_secret", raise_exception=False):
			frappe.throw(_("An HMAC Shared Secret is required to enable the external API"))
		if self.discount_precision is None or self.discount_precision < 0:
			self.discount_precision = 3
		frappe.cache().delete_value("care_card_settings")

	def on_update(self):
		frappe.cache().delete_value("care_card_settings")

