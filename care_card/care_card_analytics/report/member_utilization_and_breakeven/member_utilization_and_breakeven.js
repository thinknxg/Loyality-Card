frappe.query_reports["Member Utilization and Breakeven"] = {
	filters: [
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
		{fieldname: "only_past_breakeven", label: __("Only Past Breakeven"),
			fieldtype: "Check", default: 0},
	],
};
