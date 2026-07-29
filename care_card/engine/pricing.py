# Copyright (c) 2026, Kreatao and contributors
"""Care Card discount resolution engine.

Pure, testable, side effect free. Everything that grants value goes through
``resolve_basket``; the billing hooks and the external API are thin wrappers.

Resolution order, per line
--------------------------
1. card validity (status, paid term covers the date, beneficiary covered)
2. participating location
3. exclusions
4. insurance arbitration  — an insured line takes the co-pay share branch and
   never also takes a tier discount
5. benefit category classification
6. discount rule resolution — Item > Brand > Item Group > category default
7. caps — per line, per transaction, per category per year, per card per year
8. stacking policy against any discount already on the line
9. rounding
"""

import frappe
from frappe.utils import flt, getdate, nowdate

SPECIFICITY = {"item_code": 100, "brand": 70, "item_group": 50, "supplier": 40}


# --------------------------------------------------------------- cached masters
def get_settings():
	return frappe.get_cached_doc("Care Card Settings")


def get_categories():
	def _load():
		rows = frappe.get_all(
			"Care Benefit Category",
			filters={"is_active": 1},
			fields=["name", "priority", "margin_factor"],
			order_by="priority asc, name asc",
		)
		for row in rows:
			row["mapping"] = frappe.get_all(
				"Care Benefit Mapping",
				filters={"parent": row["name"], "parenttype": "Care Benefit Category"},
				fields=["mapping_type", "item_group", "item_code", "brand",
					"service_type", "department", "pattern"],
			)
		return rows

	return frappe.cache().get_value("care_card_categories", _load)


def get_tier_matrix(tier):
	def _load():
		out = {}
		for name in frappe.get_all("Care Card Tier", pluck="name"):
			doc = frappe.get_cached_doc("Care Card Tier", name)
			out[name] = {
				"annual_fee": flt(doc.annual_fee),
				"annual_discount_cap": flt(doc.annual_discount_cap),
				"benefits": {
					b.benefit_category: {
						"discount_type": b.discount_type,
						"discount_percent": flt(b.discount_percent),
						"discount_amount": flt(b.discount_amount),
						"min_bill_amount": flt(b.min_bill_amount),
						"max_per_txn": flt(b.max_discount_per_transaction),
						"max_per_year": flt(b.max_discount_per_year),
						"applies_to": b.applies_to or "Both",
					}
					for b in doc.benefits or []
					if b.is_active
				},
			}
		return out

	matrix = frappe.cache().get_value("care_card_tier_matrix", _load)
	return (matrix or {}).get(tier) or {"benefits": {}, "annual_discount_cap": 0}


def get_discount_rules():
	def _load():
		return frappe.get_all(
			"Care Card Discount Rule",
			filters={"is_active": 1},
			fields=["name", "rule_title", "tier", "benefit_category", "item_code", "brand",
				"item_group", "supplier", "discount_percent", "max_discount_amount",
				"min_bill_amount", "priority", "valid_from", "valid_upto"],
			order_by="priority asc",
		)

	return frappe.cache().get_value("care_card_discount_rules", _load)


def get_exclusions():
	def _load():
		return frappe.get_all(
			"Care Card Exclusion",
			filters={"is_active": 1},
			fields=["name", "exclusion_title", "applies_to", "tier", "benefit_category",
				"item_code", "item_group", "brand", "valid_from", "valid_upto", "reason"],
		)

	return frappe.cache().get_value("care_card_exclusions", _load)


def get_insurance_rules():
	def _load():
		return frappe.get_all(
			"Care Card Insurance Rule",
			filters={"is_active": 1},
			fields=["name", "rule_title", "tier", "insurance_company", "insurance_plan",
				"applies_to", "benefit_category", "copay_type", "cardholder_share_percent",
				"hospital_share_percent", "cap_per_visit", "cap_per_year", "priority",
				"valid_from", "valid_upto"],
			order_by="priority asc",
		)

	return frappe.cache().get_value("care_card_insurance_rules", _load)


def get_locations():
	def _load():
		rows = frappe.get_all(
			"Care Participating Location",
			filters={"is_active": 1},
			fields=["name", "location_type", "branch", "cost_center", "warehouse",
				"pos_profile", "healthcare_department", "external_code",
				"can_apply_discount"],
		)
		return rows

	return frappe.cache().get_value("care_card_locations", _load)


# ------------------------------------------------------------------- helpers
def _within(row, date):
	if row.get("valid_from") and getdate(row["valid_from"]) > getdate(date):
		return False
	if row.get("valid_upto") and getdate(row["valid_upto"]) < getdate(date):
		return False
	return True


def _match_scope(row, line):
	"""Return specificity score, or None when the row does not apply to the line."""
	score = 0
	for key, weight in SPECIFICITY.items():
		value = row.get(key)
		if not value:
			continue
		if str(line.get(key) or "") != str(value):
			return None
		score = max(score, weight)
	return score


def classify(line):
	"""Map a billed line to a Care Benefit Category."""
	if line.get("benefit_category"):
		return line["benefit_category"]
	for cat in get_categories() or []:
		for m in cat.get("mapping") or []:
			kind = m.get("mapping_type")
			if kind == "Item" and m.get("item_code") and line.get("item_code") == m["item_code"]:
				return cat["name"]
			if kind == "Item Group" and m.get("item_group") and line.get("item_group") == m["item_group"]:
				return cat["name"]
			if kind == "Brand" and m.get("brand") and line.get("brand") == m["brand"]:
				return cat["name"]
			if kind == "Healthcare Service Type" and m.get("service_type") \
					and line.get("service_type") == m["service_type"]:
				return cat["name"]
			if kind == "Department" and m.get("department") and line.get("department") == m["department"]:
				return cat["name"]
			if kind == "Item Code Pattern" and m.get("pattern"):
				pattern = m["pattern"].replace("%", "")
				if pattern and str(line.get("item_code") or "").startswith(pattern):
					return cat["name"]
	return None


def resolve_rule(tier, category, line, date):
	best, best_score = None, -1
	for row in get_discount_rules() or []:
		if row["benefit_category"] != category:
			continue
		if row.get("tier") and row["tier"] != tier:
			continue
		if not _within(row, date):
			continue
		if flt(row.get("min_bill_amount")) and flt(line.get("amount")) < flt(row["min_bill_amount"]):
			continue
		score = _match_scope(row, line)
		if score is None:
			continue
		# tier specific beats generic at the same scope
		score += 5 if row.get("tier") else 0
		if score > best_score:
			best, best_score = row, score
	return best


def is_excluded(tier, category, line, date):
	for row in get_exclusions() or []:
		if row.get("applies_to") == "Specific Tier" and row.get("tier") != tier:
			continue
		if not _within(row, date):
			continue
		if row.get("benefit_category") and row["benefit_category"] != category:
			continue
		scoped = any(row.get(k) for k in ("item_code", "item_group", "brand"))
		if scoped and _match_scope(row, line) is None:
			continue
		if not scoped and not row.get("benefit_category"):
			continue
		return row
	return None


def resolve_insurance_rule(tier, category, line, date):
	for row in get_insurance_rules() or []:
		if row.get("tier") and row["tier"] != tier:
			continue
		if row.get("benefit_category") and row["benefit_category"] != category:
			continue
		if row.get("insurance_company") and row["insurance_company"] != line.get("insurance_company"):
			continue
		if row.get("insurance_plan") and row["insurance_plan"] != line.get("insurance_plan"):
			continue
		if not _within(row, date):
			continue
		if row.get("applies_to") == "Non-Covered Lines":
			continue
		return row
	return None


def location_allows_discount(location_hint):
	"""location_hint is a dict of billing identifiers, or a location name."""
	locations = get_locations() or []
	if not locations:
		return None, True  # nothing configured yet: do not block go-live
	if isinstance(location_hint, str):
		for row in locations:
			if row["name"] == location_hint:
				return row["name"], bool(row.get("can_apply_discount"))
		return None, False
	hint = location_hint or {}
	for row in locations:
		for key in ("branch", "cost_center", "warehouse", "pos_profile",
				"healthcare_department", "external_code"):
			if row.get(key) and hint.get(key) and row[key] == hint[key]:
				return row["name"], bool(row.get("can_apply_discount"))
	if not any(hint.values()):
		return None, True
	return None, False


def consumed_this_year(card, term, category=None):
	"""Benefit already granted inside the current card term, from the ledger."""
	if not term:
		return 0.0
	filters = {
		"card": card,
		"is_cancelled": 0,
		"entry_type": ["in", ["Discount Given", "Co-pay Shared", "Adjustment"]],
		"posting_date": ["between", [term.from_date, term.to_date]],
	}
	if category:
		filters["benefit_category"] = category
	total = frappe.db.get_value("Care Card Ledger Entry", filters, "sum(amount)") or 0
	return abs(flt(total))


# -------------------------------------------------------------- card context
def get_card(identifier):
	"""Accept a Care Card name, a card number, a QR token or a mobile number."""
	from care_card.utils.card_number import normalise

	if not identifier:
		return None
	identifier = str(identifier).strip()
	if "." in identifier and len(identifier) > 40:
		from care_card.utils.qr import read_token

		payload = read_token(identifier)
		identifier = payload.get("cn")
	if frappe.db.exists("Care Card", identifier):
		return frappe.get_doc("Care Card", identifier)
	name = frappe.db.get_value("Care Card", {"card_number": normalise(identifier)}, "name")
	if not name:
		name = frappe.db.get_value("Care Card", {"mobile_whatsapp": identifier}, "name")
	if not name:
		parent = frappe.db.get_value("Care Card Dependent",
			{"beneficiary_code": identifier}, "parent")
		name = parent
	return frappe.get_doc("Care Card", name) if name else None


def card_eligibility(card, beneficiary_code=None, date=None):
	date = date or nowdate()
	if not card:
		return {"eligible": False, "reason": "Card not found"}
	if card.status == "Suspended":
		return {"eligible": False, "reason": "Card is suspended"}
	if card.status == "Cancelled":
		return {"eligible": False, "reason": "Card is cancelled"}
	term = None
	for row in card.terms or []:
		if row.payment_status in ("Paid", "Waived") and row.from_date and row.to_date \
				and getdate(row.from_date) <= getdate(date) <= getdate(row.to_date):
			term = row
			break
	if not term:
		return {"eligible": False, "reason": "No paid subscription term covers this date"}
	if card.status != "Active":
		return {"eligible": False, "reason": "Card status is %s" % card.status}

	beneficiary_name = card.member_name
	if beneficiary_code and beneficiary_code not in (card.card_number, card.name):
		match = [d for d in card.dependents or []
			if d.beneficiary_code == beneficiary_code and d.is_active]
		if not match:
			return {"eligible": False, "reason": "Beneficiary is not covered by this card"}
		beneficiary_name = match[0].dependent_name
		is_self = False
	else:
		beneficiary_code = card.card_number
		is_self = True
	return {
		"eligible": True,
		"reason": "",
		"term": term,
		"beneficiary_code": beneficiary_code,
		"beneficiary_name": beneficiary_name,
		"is_self": is_self,
	}


# ------------------------------------------------------------------- the engine
def resolve_basket(card_identifier, lines, beneficiary_code=None, context=None):
	"""Price a basket for a card.

	``lines`` is a list of dicts with at least ``amount``. Optional keys:
	item_code, item_name, item_group, brand, supplier, qty, rate, service_type,
	department, benefit_category, is_insured, insurance_company, insurance_plan,
	copay_percent, copay_amount, existing_discount_percent.
	"""
	context = context or {}
	date = context.get("posting_date") or nowdate()
	settings = get_settings()
	precision = int(settings.discount_precision or 3)

	card = card_identifier if hasattr(card_identifier, "doctype") else get_card(card_identifier)
	out = {
		"card": card.name if card else None,
		"card_number": card.card_number if card else None,
		"member_name": card.member_name if card else None,
		"tier": card.tier if card else None,
		"eligible": False,
		"reason": "",
		"location": None,
		"lines": [],
		"totals": {"gross": 0.0, "discount": 0.0, "copay_shared": 0.0, "net": 0.0},
	}

	elig = card_eligibility(card, beneficiary_code, date)
	out.update({
		"eligible": elig["eligible"],
		"reason": elig.get("reason") or "",
		"beneficiary_code": elig.get("beneficiary_code"),
		"beneficiary_name": elig.get("beneficiary_name"),
	})

	location, allowed = location_allows_discount(
		context.get("location") or context.get("location_hint") or {})
	out["location"] = location
	if out["eligible"] and not allowed:
		out["eligible"] = False
		out["reason"] = "Not a participating location"

	term = elig.get("term")
	tier = card.tier if card else None
	matrix = get_tier_matrix(tier) if tier else {"benefits": {}, "annual_discount_cap": 0}

	card_cap = flt(matrix.get("annual_discount_cap"))
	consumed_total = consumed_this_year(card.name, term) if (card and term) else 0.0
	category_consumed = {}
	txn_running = 0.0

	for raw in lines or []:
		line = dict(raw)
		amount = flt(line.get("amount") or flt(line.get("qty") or 1) * flt(line.get("rate") or 0))
		line["amount"] = amount
		result = {
			"item_code": line.get("item_code"),
			"item_name": line.get("item_name") or line.get("item_code"),
			"qty": flt(line.get("qty") or 1),
			"rate": flt(line.get("rate") or 0),
			"gross_amount": amount,
			"benefit_category": None,
			"discount_percent": 0.0,
			"discount_amount": 0.0,
			"copay_shared": 0.0,
			"is_insured": 1 if line.get("is_insured") else 0,
			"net_amount": amount,
			"rule_applied": None,
			"explanation": "",
		}

		if not out["eligible"]:
			result["explanation"] = out["reason"] or "Card not eligible"
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["net"] += amount
			continue

		category = classify(line)
		result["benefit_category"] = category
		if not category:
			result["explanation"] = "No benefit category matches this item"
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["net"] += amount
			continue

		exclusion = is_excluded(tier, category, line, date)
		if exclusion:
			result["explanation"] = "Excluded: %s" % (exclusion.get("reason")
				or exclusion.get("exclusion_title"))
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["net"] += amount
			continue

		benefit = (matrix.get("benefits") or {}).get(category)
		if benefit and benefit.get("applies_to") != "Both":
			wants_self = benefit["applies_to"] == "Self"
			if wants_self != bool(elig.get("is_self")):
				result["explanation"] = "Benefit applies to %s only" % benefit["applies_to"]
				out["lines"].append(result)
				out["totals"]["gross"] += amount
				out["totals"]["net"] += amount
				continue

		# ---------------------------------------------------- insurance branch
		if line.get("is_insured"):
			rule = resolve_insurance_rule(tier, category, line, date)
			if not rule:
				result["explanation"] = ("Insured line — card discounts cannot be combined "
					"with insurance benefits")
			else:
				copay = flt(line.get("copay_amount"))
				if not copay and flt(line.get("copay_percent")):
					copay = amount * flt(line["copay_percent"]) / 100.0
				if copay <= 0:
					result["explanation"] = "Insured line with no co-payment to share"
				else:
					hospital_share = flt(rule.get("hospital_share_percent"))
					if not hospital_share:
						hospital_share = 100 - flt(rule.get("cardholder_share_percent"))
					shared = copay * hospital_share / 100.0
					if flt(rule.get("cap_per_visit")):
						shared = min(shared, flt(rule["cap_per_visit"]) - txn_running)
					if flt(rule.get("cap_per_year")):
						remaining = flt(rule["cap_per_year"]) - consumed_total
						shared = min(shared, max(remaining, 0))
					shared = max(round(shared, precision), 0)
					result["copay_shared"] = shared
					result["rule_applied"] = rule["name"]
					result["explanation"] = (
						"Insured line. Co-payment %s shared %s%% by the hospital under %s"
						% (round(copay, precision), round(hospital_share, 2), rule["rule_title"]))
					txn_running += shared
					consumed_total += shared
			result["net_amount"] = amount
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["copay_shared"] += result["copay_shared"]
			out["totals"]["net"] += amount
			continue

		# ------------------------------------------------------ discount branch
		if not benefit:
			result["explanation"] = "Tier %s has no benefit for %s" % (tier, category)
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["net"] += amount
			continue

		if flt(benefit.get("min_bill_amount")) and amount < flt(benefit["min_bill_amount"]):
			result["explanation"] = "Below the minimum line amount for %s" % category
			out["lines"].append(result)
			out["totals"]["gross"] += amount
			out["totals"]["net"] += amount
			continue

		rule = resolve_rule(tier, category, line, date)
		if rule:
			percent = flt(rule["discount_percent"])
			source = "rule %s" % rule["rule_title"]
			result["rule_applied"] = rule["name"]
			line_cap = flt(rule.get("max_discount_amount")) or flt(benefit.get("max_per_txn"))
		else:
			if benefit["discount_type"] == "Fixed Amount":
				percent = (flt(benefit["discount_amount"]) / amount * 100.0) if amount else 0
			else:
				percent = flt(benefit["discount_percent"])
			source = "tier benefit %s" % category
			line_cap = flt(benefit.get("max_per_txn"))

		discount = amount * percent / 100.0

		# stacking policy
		existing = flt(line.get("existing_discount_percent"))
		if existing:
			policy = settings.stacking_policy or "Greater Of Two"
			if policy == "No Card Discount":
				result["explanation"] = "Line already discounted; card discount not applied"
				out["lines"].append(result)
				out["totals"]["gross"] += amount
				out["totals"]["net"] += amount
				continue
			if policy == "Greater Of Two" and existing >= percent:
				result["explanation"] = ("Existing %s%% offer is better than the card's %s%%; "
					"card discount not applied" % (round(existing, 2), round(percent, 2)))
				out["lines"].append(result)
				out["totals"]["gross"] += amount
				out["totals"]["net"] += amount
				continue

		caps = []
		if line_cap:
			caps.append(("per transaction cap", line_cap))
		if flt(benefit.get("max_per_year")):
			used = category_consumed.get(category)
			if used is None:
				used = consumed_this_year(card.name, term, category) if term else 0.0
				category_consumed[category] = used
			caps.append(("annual cap for %s" % category,
				max(flt(benefit["max_per_year"]) - used, 0)))
		if card_cap:
			caps.append(("annual card cap", max(card_cap - consumed_total, 0)))

		capped_by = None
		for label, ceiling in caps:
			if discount > ceiling:
				discount = ceiling
				capped_by = label

		discount = max(round(discount, precision), 0)
		effective = (discount / amount * 100.0) if amount else 0

		result["discount_percent"] = round(effective, 2)
		result["discount_amount"] = discount
		result["net_amount"] = round(amount - discount, precision)
		result["explanation"] = "%s%% via %s%s" % (
			round(percent, 2), source, (" — limited by %s" % capped_by) if capped_by else "")

		if category in category_consumed:
			category_consumed[category] += discount
		consumed_total += discount
		txn_running += discount

		out["lines"].append(result)
		out["totals"]["gross"] += amount
		out["totals"]["discount"] += discount
		out["totals"]["net"] += result["net_amount"]

	for key in out["totals"]:
		out["totals"][key] = round(flt(out["totals"][key]), precision)
	out["totals"]["total_benefit"] = round(
		out["totals"]["discount"] + out["totals"]["copay_shared"], precision)
	return out


@frappe.whitelist()
def quote(card, lines, beneficiary_code=None, context=None):
	"""Whitelisted wrapper used by the desk, the POS script and the portal."""
	if isinstance(lines, str):
		lines = frappe.parse_json(lines)
	if isinstance(context, str):
		context = frappe.parse_json(context)
	return resolve_basket(card, lines, beneficiary_code=beneficiary_code, context=context)
