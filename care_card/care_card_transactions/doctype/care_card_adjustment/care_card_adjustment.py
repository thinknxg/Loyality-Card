# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardAdjustment(Document):
	def validate(self):
		if not self.approved_by:
			self.approved_by = frappe.session.user

	def on_submit(self):
		from care_card.ledger import post_adjustment
		post_adjustment(self)
		frappe.enqueue("care_card.analytics.refresh_card", card=self.card,
			queue="short", enqueue_after_commit=True)

	def on_cancel(self):
		from care_card.ledger import reverse_reference
		reverse_reference(self.doctype, self.name, remarks=_("Adjustment cancelled"))
		frappe.enqueue("care_card.analytics.refresh_card", card=self.card,
			queue="short", enqueue_after_commit=True)

