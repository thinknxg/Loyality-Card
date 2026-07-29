# Copyright (c) 2026, Kreatao and contributors
"""Post-install setup.

Everything here is idempotent and defensive: the app must install cleanly on a
bare Frappe bench (external HIS mode) and light up the ERPNext bindings when
ERPNext / Healthcare happen to be present.
"""

import frappe
from frappe import _

ROLES = [
	("Care Card Manager", "Full control of the program, rates and adjustments"),
	("Care Card Sales Agent", "Sells and activates cards at a counter"),
	("Care Card Hospital Cashier", "Applies card discounts on hospital bills"),
	("Care Card Pharmacy Cashier", "Applies card discounts on pharmacy bills"),
	("Care Card Auditor", "Read only access to every record and report"),
	("Care Card Insurance Coordinator", "Maintains co-payment sharing rules"),
]

SETUP_DOCTYPES = [
	"Care Card Program", "Care Card Tier", "Care Benefit Category",
	"Care Card Discount Rule", "Care Card Exclusion", "Care Participating Location",
	"Care Card Settings",
]
MEMBERSHIP_DOCTYPES = ["Care Card", "Care Card Application", "Care Card Digital Asset"]
TXN_DOCTYPES = ["Care Card Usage", "Care Card Ledger Entry", "Care Card Adjustment"]
COMM_DOCTYPES = ["Care Card Message Template", "Care Card Message Log"]
INSURANCE_DOCTYPES = ["Care Card Insurance Rule"]
ALL_DOCTYPES = (SETUP_DOCTYPES + MEMBERSHIP_DOCTYPES + TXN_DOCTYPES
	+ COMM_DOCTYPES + INSURANCE_DOCTYPES)

# (doctype, fieldname, target doctype) — Data fields promoted to Links when the
# target exists. Keeps the shipped JSON installable without ERPNext.
LINK_UPGRADES = [
	("Care Card Program", "company", "Company"),
	("Care Card Settings", "default_company", "Company"),
	("Care Card Tier", "fee_item", "Item"),
	("Care Benefit Mapping", "item_group", "Item Group"),
	("Care Benefit Mapping", "item_code", "Item"),
	("Care Benefit Mapping", "brand", "Brand"),
	("Care Benefit Mapping", "service_type", "Healthcare Service Unit Type"),
	("Care Benefit Mapping", "department", "Medical Department"),
	("Care Card Discount Rule", "item_code", "Item"),
	("Care Card Discount Rule", "brand", "Brand"),
	("Care Card Discount Rule", "item_group", "Item Group"),
	("Care Card Discount Rule", "supplier", "Supplier"),
	("Care Card Exclusion", "item_code", "Item"),
	("Care Card Exclusion", "item_group", "Item Group"),
	("Care Card Exclusion", "brand", "Brand"),
	("Care Participating Location", "company", "Company"),
	("Care Participating Location", "branch", "Branch"),
	("Care Participating Location", "cost_center", "Cost Center"),
	("Care Participating Location", "warehouse", "Warehouse"),
	("Care Participating Location", "pos_profile", "POS Profile"),
	("Care Participating Location", "healthcare_department", "Medical Department"),
	("Care Card", "customer", "Customer"),
	("Care Card", "patient", "Patient"),
	("Care Card", "company", "Company"),
	("Care Card Dependent", "patient", "Patient"),
	("Care Card Term", "sales_invoice", "Sales Invoice"),
	("Care Card Insurance Rule", "insurance_company", "Healthcare Insurance Company"),
]


# ------------------------------------------------------------------ entrypoint
def after_install():
	create_roles()
	create_custom_fields()
	upgrade_link_fields()
	seed_program()
	seed_categories()
	seed_tiers()
	seed_otc_rules()
	seed_exclusions()
	seed_insurance_rule()
	seed_templates()
	configure_settings()
	assign_permissions()
	add_report_roles()
	create_dashboard_objects()
	frappe.db.commit()
	frappe.clear_cache()
	print("Care Card installed. Open the Care Card workspace to review rates.")


def before_uninstall():
	try:
		from frappe.custom.doctype.custom_field.custom_field import CustomField  # noqa: F401

		for name in frappe.get_all("Custom Field",
				filters={"module": "Care Card Setup"}, pluck="name"):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		for name in frappe.get_all("Property Setter",
				filters={"module": "Care Card Setup"}, pluck="name"):
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Care Card: uninstall cleanup failed")


# ----------------------------------------------------------------------- roles
def create_roles():
	for role, description in ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.new_doc("Role")
		doc.role_name = role
		doc.desk_access = 1
		if frappe.get_meta("Role").has_field("description"):
			doc.description = description
		doc.insert(ignore_permissions=True)


def _grant(doctype, role, **flags):
	from frappe.permissions import add_permission, update_permission_property

	if not frappe.db.exists("DocType", doctype):
		return
	add_permission(doctype, role, 0)
	for key, value in flags.items():
		update_permission_property(doctype, role, 0, key, 1 if value else 0)


def assign_permissions():
	full = {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1,
		"share": 1, "print": 1, "email": 1, "submit": 1, "cancel": 1, "amend": 1}
	read_only = {"read": 1, "report": 1, "export": 1, "print": 1, "email": 1}
	operate = {"read": 1, "write": 1, "create": 1, "report": 1, "print": 1, "submit": 1}

	for doctype in ALL_DOCTYPES:
		_grant(doctype, "Care Card Manager", **full)
		_grant(doctype, "Care Card Auditor", **read_only)

	for doctype in ["Care Card", "Care Card Application", "Care Card Digital Asset",
			"Care Card Tier", "Care Card Program"]:
		_grant(doctype, "Care Card Sales Agent",
			**(operate if doctype in ("Care Card", "Care Card Application") else read_only))

	for role in ("Care Card Hospital Cashier", "Care Card Pharmacy Cashier"):
		_grant("Care Card", role, read=1, write=1, report=1, print=1)
		_grant("Care Card Usage", role, **operate)
		_grant("Care Card Tier", role, **read_only)
		_grant("Care Benefit Category", role, **read_only)
		_grant("Care Card Discount Rule", role, **read_only)

	for doctype in ["Care Card Insurance Rule", "Care Card Usage", "Care Card Ledger Entry"]:
		_grant(doctype, "Care Card Insurance Coordinator",
			**(full if doctype == "Care Card Insurance Rule" else read_only))


# --------------------------------------------------------------- custom fields
def create_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import (
		create_custom_fields as _create,
	)

	parent_fields = [
		{"fieldname": "care_card_section", "label": "Care Card", "fieldtype": "Section Break",
			"insert_after": "customer_name", "collapsible": 1},
		{"fieldname": "care_card", "label": "Care Card", "fieldtype": "Link",
			"options": "Care Card", "insert_after": "care_card_section"},
		{"fieldname": "care_card_beneficiary", "label": "Beneficiary Code", "fieldtype": "Data",
			"insert_after": "care_card", "depends_on": "care_card"},
		{"fieldname": "care_card_beneficiary_name", "label": "Beneficiary", "fieldtype": "Data",
			"insert_after": "care_card_beneficiary", "read_only": 1, "depends_on": "care_card"},
		{"fieldname": "care_card_location", "label": "Care Card Location", "fieldtype": "Link",
			"options": "Care Participating Location", "insert_after": "care_card_beneficiary_name"},
		{"fieldname": "care_card_col", "fieldtype": "Column Break",
			"insert_after": "care_card_location"},
		{"fieldname": "care_card_tier", "label": "Tier", "fieldtype": "Data",
			"insert_after": "care_card_col", "read_only": 1, "depends_on": "care_card"},
		{"fieldname": "care_card_status", "label": "Card Status", "fieldtype": "Data",
			"insert_after": "care_card_tier", "read_only": 1, "depends_on": "care_card"},
		{"fieldname": "care_card_discount_total", "label": "Card Discount", "fieldtype": "Currency",
			"insert_after": "care_card_status", "read_only": 1, "depends_on": "care_card"},
		{"fieldname": "care_card_copay_shared", "label": "Co-pay Shared", "fieldtype": "Currency",
			"insert_after": "care_card_discount_total", "read_only": 1, "depends_on": "care_card"},
		{"fieldname": "cc_insurance_company", "label": "Insurance Company (Card)",
			"fieldtype": "Data", "insert_after": "care_card_copay_shared", "depends_on": "care_card"},
		{"fieldname": "cc_insurance_plan", "label": "Insurance Plan (Card)", "fieldtype": "Data",
			"insert_after": "cc_insurance_company", "depends_on": "care_card"},
	]

	item_fields = [
		{"fieldname": "cc_section", "label": "Care Card", "fieldtype": "Section Break",
			"insert_after": "item_tax_template", "collapsible": 1},
		{"fieldname": "cc_benefit_category", "label": "Benefit Category", "fieldtype": "Link",
			"options": "Care Benefit Category", "insert_after": "cc_section", "read_only": 1},
		{"fieldname": "cc_discount_amount", "label": "Card Discount Amount",
			"fieldtype": "Currency", "insert_after": "cc_benefit_category", "read_only": 1},
		{"fieldname": "cc_copay_shared", "label": "Co-pay Shared", "fieldtype": "Currency",
			"insert_after": "cc_discount_amount", "read_only": 1},
		{"fieldname": "cc_rule_applied", "label": "Rule Applied", "fieldtype": "Data",
			"insert_after": "cc_copay_shared", "read_only": 1},
		{"fieldname": "cc_col", "fieldtype": "Column Break", "insert_after": "cc_rule_applied"},
		{"fieldname": "cc_is_insured", "label": "Covered by Insurance", "fieldtype": "Check",
			"insert_after": "cc_col"},
		{"fieldname": "cc_copay_percent", "label": "Co-payment %", "fieldtype": "Percent",
			"insert_after": "cc_is_insured", "depends_on": "cc_is_insured"},
		{"fieldname": "cc_copay_amount", "label": "Co-payment Amount", "fieldtype": "Currency",
			"insert_after": "cc_copay_percent", "depends_on": "cc_is_insured"},
		{"fieldname": "cc_existing_discount_percent", "label": "Other Offer %",
			"fieldtype": "Percent", "insert_after": "cc_copay_amount"},
		{"fieldname": "cc_service_type", "label": "Service Type", "fieldtype": "Data",
			"insert_after": "cc_existing_discount_percent"},
		{"fieldname": "cc_explanation", "label": "Discount Explanation", "fieldtype": "Small Text",
			"insert_after": "cc_service_type", "read_only": 1},
	]

	spec = {}
	for parent in ("Sales Invoice", "POS Invoice", "Sales Order", "Quotation"):
		if frappe.db.exists("DocType", parent):
			spec[parent] = [dict(f, module="Care Card Setup") for f in parent_fields]
	for child in ("Sales Invoice Item", "POS Invoice Item", "Sales Order Item", "Quotation Item"):
		if frappe.db.exists("DocType", child):
			spec[child] = [dict(f, module="Care Card Setup") for f in item_fields]

	for patient_dt in ("Patient", "Patient Appointment", "Patient Encounter"):
		if frappe.db.exists("DocType", patient_dt):
			spec[patient_dt] = [{
				"fieldname": "care_card", "label": "Care Card", "fieldtype": "Link",
				"options": "Care Card", "insert_after": "status", "module": "Care Card Setup",
			}]

	if spec:
		_create(spec, ignore_validate=True)


def upgrade_link_fields():
	"""Promote Data placeholders to real Links wherever the target doctype exists."""
	done = 0
	for doctype, fieldname, target in LINK_UPGRADES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if not frappe.db.exists("DocType", target):
			continue
		meta = frappe.get_meta(doctype)
		field = meta.get_field(fieldname)
		if not field or field.fieldtype != "Data":
			continue
		try:
			frappe.make_property_setter({
				"doctype": doctype, "doctype_or_field": "DocField", "fieldname": fieldname,
				"property": "fieldtype", "value": "Link", "property_type": "Data",
			}, ignore_validate=True, validate_fields_for_doctype=False)
			frappe.make_property_setter({
				"doctype": doctype, "doctype_or_field": "DocField", "fieldname": fieldname,
				"property": "options", "value": target, "property_type": "Text",
			}, ignore_validate=True, validate_fields_for_doctype=False)
			done += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(),
				"Care Card: link upgrade failed for %s.%s" % (doctype, fieldname))

	if done and frappe.db.has_column("Property Setter", "module"):
		frappe.db.sql("""
			update `tabProperty Setter` set module='Care Card Setup'
			where doc_type like 'Care %%' and (module is null or module='')
		""")


# ------------------------------------------------------------------ seed data
PROGRAM = "Care Card Program"

CATEGORIES = [
	# name, abbr, priority, margin factor, item group, code pattern
	("Consultation", "CONS", 10, 30, "Consultation", "CONS-"),
	("Lab Investigation", "LAB", 20, 45, "Lab Test", "LAB-"),
	("Radiology Investigation", "RAD", 30, 40, "Radiology", "RAD-"),
	("Inpatient Treatment", "IP", 40, 55, "Inpatient", "IP-"),
	("Prescription Medication", "RX", 50, 100, "Prescription Medication", "RX-"),
	("OTC Medication", "OTC", 60, 100, "OTC Medication", "OTC-"),
]

TIERS = [
	{
		"tier_name": "Gold", "annual_fee": 25, "sort_order": 10, "max_dependents": 4,
		"card_colour": "#C9A227", "card_accent": "#7A6212",
		"tagline": "Everyday cover for you and your family",
		"benefits": {
			"Consultation": 20, "Lab Investigation": 25, "Radiology Investigation": 20,
			"Inpatient Treatment": 15, "Prescription Medication": 5, "OTC Medication": 5,
		},
	},
	{
		"tier_name": "Platinum", "annual_fee": 40, "sort_order": 20, "max_dependents": 6,
		"card_colour": "#6E7B8B", "card_accent": "#3A4450",
		"tagline": "Deeper cover across the hospital and pharmacy",
		"benefits": {
			"Consultation": 30, "Lab Investigation": 35, "Radiology Investigation": 30,
			"Inpatient Treatment": 25, "Prescription Medication": 15, "OTC Medication": 15,
		},
	},
]

# OTC bands — Gold 5..35, Platinum 15..45, exactly as the program terms describe.
OTC_BANDS = [
	("OTC - Personal Care", 5, 15),
	("OTC - Vitamins & Supplements", 15, 25),
	("OTC - Baby Care", 20, 30),
	("OTC - First Aid", 25, 35),
	("OTC - Medical Devices", 35, 45),
]


def seed_program():
	if frappe.db.exists("Care Card Program", PROGRAM):
		return
	doc = frappe.new_doc("Care Card Program")
	doc.name = PROGRAM
	doc.program_name = PROGRAM
	doc.currency = "OMR" if frappe.db.exists("Currency", "OMR") else frappe.db.get_value(
		"Currency", {"enabled": 1}, "name") or "OMR"
	doc.validity_months = 12
	doc.grace_period_days = 7
	doc.max_dependents = 6
	doc.require_civil_id = 1
	doc.allow_physical_card = 1
	doc.is_active = 1
	for days in (30, 15, 7, 1):
		doc.append("reminder_schedule", {"days_before_expiry": days,
			"channel": "WhatsApp", "is_active": 1})
	doc.terms_and_conditions = (
		"<p>The card is valid for one year from the date of activation and is "
		"non-transferable. It must be presented at the time of service or purchase. "
		"Discounts apply only at participating hospital departments and pharmacies and "
		"cannot be combined with other offers, insurance benefits or government subsidies "
		"unless explicitly stated. The card is not health insurance and does not replace "
		"medical advice. The hospital and its pharmacies may amend the covered services "
		"and discount percentages with prior notice.</p>")
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


def seed_categories():
	for name, abbr, priority, margin, item_group, pattern in CATEGORIES:
		if frappe.db.exists("Care Benefit Category", name):
			continue
		doc = frappe.new_doc("Care Benefit Category")
		doc.category_name = name
		doc.abbr = abbr
		doc.priority = priority
		doc.margin_factor = margin
		doc.is_active = 1
		doc.description = _("Seeded by Care Card. Edit the mapping to match your item groups.")
		doc.append("mapping", {"mapping_type": "Item Group", "item_group": item_group})
		doc.append("mapping", {"mapping_type": "Item Code Pattern", "pattern": pattern + "%"})
		doc.insert(ignore_permissions=True)


def seed_tiers():
	for spec in TIERS:
		if frappe.db.exists("Care Card Tier", spec["tier_name"]):
			continue
		doc = frappe.new_doc("Care Card Tier")
		doc.tier_name = spec["tier_name"]
		doc.program = PROGRAM
		doc.annual_fee = spec["annual_fee"]
		doc.sort_order = spec["sort_order"]
		doc.max_dependents = spec["max_dependents"]
		doc.include_self = 1
		doc.is_active = 1
		doc.card_colour = spec["card_colour"]
		doc.card_accent = spec["card_accent"]
		doc.tagline = spec["tagline"]
		for category, percent in spec["benefits"].items():
			doc.append("benefits", {
				"benefit_category": category,
				"discount_type": "Percentage",
				"discount_percent": percent,
				"applies_to": "Both",
				"is_active": 1,
			})
		doc.insert(ignore_permissions=True)


def seed_otc_rules():
	for item_group, gold, platinum in OTC_BANDS:
		for tier, percent in (("Gold", gold), ("Platinum", platinum)):
			title = "%s — %s" % (tier, item_group)
			if frappe.db.exists("Care Card Discount Rule", {"rule_title": title}):
				continue
			doc = frappe.new_doc("Care Card Discount Rule")
			doc.rule_title = title
			doc.tier = tier
			doc.benefit_category = "OTC Medication"
			doc.item_group = item_group
			doc.discount_percent = percent
			doc.priority = 10
			doc.is_active = 1
			doc.notes = _("Seeded OTC band. Repoint item_group at your own pharmacy groups.")
			doc.insert(ignore_permissions=True)


def seed_exclusions():
	defaults = [
		("Government subsidised items", "Government Subsidised",
			_("Program terms exclude government subsidised items.")),
		("Implants and prosthetics", "Implants",
			_("High value pass-through items are excluded from card discounts.")),
		("Vaccines", "Vaccines", _("Vaccination programmes are priced separately.")),
	]
	for title, item_group, reason in defaults:
		if frappe.db.exists("Care Card Exclusion", title):
			continue
		doc = frappe.new_doc("Care Card Exclusion")
		doc.exclusion_title = title
		doc.applies_to = "All Tiers"
		doc.item_group = item_group
		doc.reason = reason
		doc.is_active = 1
		doc.insert(ignore_permissions=True)


def seed_insurance_rule():
	title = "Default co-payment sharing"
	if frappe.db.exists("Care Card Insurance Rule", title):
		return
	doc = frappe.new_doc("Care Card Insurance Rule")
	doc.rule_title = title
	doc.applies_to = "Insured Covered Lines"
	doc.copay_type = "Percentage"
	doc.cardholder_share_percent = 50
	doc.priority = 100
	doc.is_active = 1
	doc.notes = _("A 10% co-payment becomes 5% payable by the cardholder and 5% absorbed "
		"by the hospital. Card discounts are never applied on insured lines.")
	doc.insert(ignore_permissions=True)


TEMPLATES = [
	("Card Activation EN", "Card Activation", "en",
		"Your Care Card is active",
		"Hello {{ member_name }}, your {{ tier }} Care Card {{ card_number }} is now active "
		"until {{ expiry_date }}. Show this card at any participating hospital department or "
		"pharmacy to receive your discounts. View it any time: {{ card_url }}"),
	("Card Activation AR", "Card Activation", "ar",
		"بطاقتك الصحية مفعّلة",
		"مرحباً {{ member_name }}، بطاقة {{ tier }} رقم {{ card_number }} مفعّلة حتى "
		"{{ expiry_date }}. يرجى إبراز البطاقة عند تلقي الخدمة أو الشراء. "
		"لعرض البطاقة: {{ card_url }}"),
	("Renewal Reminder EN", "Renewal Reminder", "en",
		"Your Care Card expires soon",
		"Hello {{ member_name }}, your {{ tier }} Care Card {{ card_number }} expires on "
		"{{ expiry_date }} ({{ days_left }} days left). Renew online at {{ card_url }} or at "
		"any hospital counter."),
	("Renewal Reminder AR", "Renewal Reminder", "ar",
		"تذكير بتجديد البطاقة",
		"مرحباً {{ member_name }}، تنتهي صلاحية بطاقتك {{ card_number }} بتاريخ "
		"{{ expiry_date }} (متبقٍ {{ days_left }} يوماً). يمكنك التجديد عبر {{ card_url }}."),
	("Renewal Confirmed EN", "Renewal Confirmed", "en",
		"Care Card renewed",
		"Thank you {{ member_name }}. Your {{ tier }} Care Card {{ card_number }} is renewed "
		"until {{ expiry_date }}."),
	("Card Expired EN", "Card Expired", "en",
		"Your Care Card has expired",
		"Hello {{ member_name }}, Care Card {{ card_number }} expired on {{ expiry_date }}. "
		"Renew at {{ card_url }} to keep your family's discounts active."),
	("Usage Receipt EN", "Usage Receipt", "en",
		"Care Card savings",
		"Hello {{ member_name }}, you saved {{ saved }} on your visit today using Care Card "
		"{{ card_number }}. Total saved this year: {{ total_saved }}."),
	("Dependent Added EN", "Dependent Added", "en",
		"Family member added",
		"Hello {{ member_name }}, {{ dependent_name }} is now covered by your Care Card "
		"{{ card_number }}."),
	("OTP EN", "OTP", "en", "Care Card verification",
		"Your Care Card verification code is {{ otp }}. It expires in 5 minutes."),
]


def seed_templates():
	for name, event, language, subject, message in TEMPLATES:
		if frappe.db.exists("Care Card Message Template", name):
			continue
		doc = frappe.new_doc("Care Card Message Template")
		doc.template_name = name
		doc.event = event
		doc.channel = "WhatsApp"
		doc.language = language
		doc.is_active = 1
		doc.subject = subject
		doc.message = message
		doc.attach_card_image = 1 if event in ("Card Activation", "Renewal Confirmed") else 0
		doc.variable_order = "member_name,tier,card_number,expiry_date,card_url"
		doc.insert(ignore_permissions=True)


def configure_settings():
	settings = frappe.get_single("Care Card Settings")
	settings.enabled = 1
	settings.default_program = PROGRAM
	settings.stacking_policy = settings.stacking_policy or "Greater Of Two"
	settings.apply_before_tax = 1
	settings.discount_precision = 3
	settings.block_expired_cards = 1
	settings.card_number_prefix = settings.card_number_prefix or "97"
	settings.card_base_url = settings.card_base_url or "/my-card"
	settings.default_language = settings.default_language or "en"
	settings.mask_civil_id = 1
	settings.require_consent = 1
	settings.retention_years = settings.retention_years or 7
	settings.message_retry_limit = settings.message_retry_limit or 3
	settings.api_timestamp_tolerance = settings.api_timestamp_tolerance or 300
	if not settings.get_password("qr_secret", raise_exception=False):
		settings.qr_secret = frappe.generate_hash(length=48)
	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)


def add_report_roles():
	"""Reports ship with System Manager only (custom roles do not exist at sync time)."""
	reports = frappe.get_all("Report", filters={"module": "Care Card Analytics"}, pluck="name")
	for name in reports:
		try:
			doc = frappe.get_doc("Report", name)
			have = {r.role for r in doc.roles}
			changed = False
			for role in ("Care Card Manager", "Care Card Auditor"):
				if role not in have and frappe.db.exists("Role", role):
					doc.append("roles", {"role": role})
					changed = True
			if changed:
				doc.flags.ignore_permissions = True
				doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Care Card: report roles not updated")


# ---------------------------------------------------------------- dashboards
NUMBER_CARDS = [
	("Care Card - Active Cards", "Care Card", "Count", None,
		'[["Care Card","status","=","Active"]]'),
	("Care Card - Cards Past Breakeven", "Care Card", "Count", None,
		'[["Care Card","breakeven_date","is","set"]]'),
	("Care Card - Fees Collected", "Care Card Ledger Entry", "Sum", "amount",
		'[["Care Card Ledger Entry","entry_type","=","Fee Collected"],'
		'["Care Card Ledger Entry","is_cancelled","=",0]]'),
	("Care Card - Discount Granted", "Care Card Ledger Entry", "Sum", "amount",
		'[["Care Card Ledger Entry","entry_type","=","Discount Given"],'
		'["Care Card Ledger Entry","is_cancelled","=",0]]'),
	("Care Card - Co-pay Shared", "Care Card Ledger Entry", "Sum", "amount",
		'[["Care Card Ledger Entry","entry_type","=","Co-pay Shared"],'
		'["Care Card Ledger Entry","is_cancelled","=",0]]'),
	("Care Card - Economic Cost", "Care Card Ledger Entry", "Sum", "margin_cost",
		'[["Care Card Ledger Entry","is_cancelled","=",0]]'),
]

CHARTS = [
	("Care Card - Cards Sold", "Care Card", "Count", None, "creation", "Line", "Monthly"),
	("Care Card - Benefit by Category", "Care Card Ledger Entry", "Sum", "amount",
		"benefit_category", "Bar", None),
	("Care Card - Usage Trend", "Care Card Usage", "Sum", "total_discount",
		"posting_date", "Line", "Monthly"),
]


def create_dashboard_objects():
	try:
		for label, doctype, func, field, filters in NUMBER_CARDS:
			if frappe.db.exists("Number Card", label):
				continue
			doc = frappe.new_doc("Number Card")
			doc.label = label
			doc.name = label
			doc.document_type = doctype
			doc.function = func
			if field:
				doc.aggregate_function_based_on = field
			doc.filters_json = filters
			doc.is_public = 1
			doc.show_percentage_stats = 1
			doc.stats_time_interval = "Monthly"
			doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Care Card: number cards not created")

	try:
		for label, doctype, func, field, based_on, chart_type, interval in CHARTS:
			if frappe.db.exists("Dashboard Chart", label):
				continue
			doc = frappe.new_doc("Dashboard Chart")
			doc.chart_name = label
			doc.name = label
			doc.document_type = doctype
			doc.chart_type = "Group By" if not interval else "Sum" if field else "Count"
			if interval:
				doc.chart_type = "Sum" if field else "Count"
				doc.based_on = based_on
				doc.time_interval = interval
				doc.timespan = "Last Year"
				if field:
					doc.value_based_on = field
			else:
				doc.chart_type = "Group By"
				doc.group_by_type = "Sum"
				doc.group_by_based_on = based_on
				doc.aggregate_function_based_on = field
			doc.type = chart_type
			doc.is_public = 1
			doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Care Card: dashboard charts not created")
