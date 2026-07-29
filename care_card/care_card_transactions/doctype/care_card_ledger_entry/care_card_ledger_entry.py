# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareCardLedgerEntry(Document):
	def on_update(self):
		if self.flags.ignore_immutable or self.flags.in_insert:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		mutable = {"is_cancelled", "cancelled_by_entry", "modified", "modified_by"}
		for key in ("amount", "entry_type", "card", "posting_date", "benefit_category"):
			if before.get(key) != self.get(key):
				frappe.throw(_("Ledger entries are immutable. Post a reversal instead."))
		_ = mutable

	def on_trash(self):
		if frappe.session.user != "Administrator" and not self.flags.ignore_immutable:
			frappe.throw(_("Ledger entries cannot be deleted. Post a reversal instead."))

