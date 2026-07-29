# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CareParticipatingLocation(Document):
	def validate(self):
		frappe.cache().delete_value("care_card_locations")

	def on_trash(self):
		frappe.cache().delete_value("care_card_locations")

