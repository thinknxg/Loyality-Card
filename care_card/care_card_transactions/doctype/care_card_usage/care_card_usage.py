# Copyright (c) 2026, Kreatao and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate
from frappe.model.document import Document


class CareCardUsage(Document):
	def validate(self):
		if self.posting_datetime:
			self.posting_date = getdate(self.posting_datetime)
		if not self.posted_by:
			self.posted_by = frappe.session.user
		self.calculate_totals()
		self.validate_card()

	def validate_card(self):
		card = frappe.get_cached_doc("Care Card", self.card)
		if card.status == "Cancelled":
			frappe.throw(_("Card {0} is cancelled").format(self.card))
		if self.beneficiary_code and self.beneficiary_code != card.card_number:
			codes = [d.beneficiary_code for d in card.dependents if d.is_active]
			if self.beneficiary_code not in codes:
				frappe.throw(_("Beneficiary {0} is not covered by card {1}")
					.format(self.beneficiary_code, self.card))

	def calculate_totals(self):
		from care_card.analytics import margin_factor_for
		gross = disc = copay = econ = 0.0
		for row in self.lines or []:
			row.gross_amount = flt(row.gross_amount or (flt(row.qty) * flt(row.rate)))
			row.discount_amount = flt(row.discount_amount)
			row.copay_shared = flt(row.copay_shared)
			row.net_amount = flt(row.gross_amount - row.discount_amount)
			gross += row.gross_amount
			disc += row.discount_amount
			copay += row.copay_shared
			factor = margin_factor_for(row.benefit_category)
			econ += (row.discount_amount + row.copay_shared) * factor / 100.0
		self.gross_amount = gross
		self.total_discount = disc
		self.copay_shared = copay
		self.net_amount = gross - disc
		self.economic_cost = econ

	def on_submit(self):
		from care_card.ledger import post_usage
		post_usage(self)
		frappe.enqueue("care_card.analytics.refresh_card", card=self.card,
			queue="short", enqueue_after_commit=True)

	def on_cancel(self):
		from care_card.ledger import reverse_usage
		reverse_usage(self)
		frappe.enqueue("care_card.analytics.refresh_card", card=self.card,
			queue="short", enqueue_after_commit=True)

