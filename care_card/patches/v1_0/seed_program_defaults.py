# Copyright (c) 2026, Kreatao and contributors
"""Re-run the idempotent seeders so upgrades pick up new defaults."""

import frappe


def execute():
	from care_card.install import (
		assign_permissions,
		create_custom_fields,
		create_roles,
		seed_categories,
		seed_exclusions,
		seed_insurance_rule,
		seed_otc_rules,
		seed_program,
		seed_templates,
		seed_tiers,
		upgrade_link_fields,
	)

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
	assign_permissions()
	frappe.db.commit()
