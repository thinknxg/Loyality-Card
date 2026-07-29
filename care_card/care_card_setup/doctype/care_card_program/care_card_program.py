# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardProgram(Document):
	def validate(self):
		if self.validity_months and self.validity_months < 1:
			frappe.throw(_("Validity (Months) must be at least 1"))
		seen = set()
		for row in self.reminder_schedule or []:
			if row.days_before_expiry in seen:
				frappe.throw(_("Duplicate reminder at {0} days before expiry").format(row.days_before_expiry))
			seen.add(row.days_before_expiry)

