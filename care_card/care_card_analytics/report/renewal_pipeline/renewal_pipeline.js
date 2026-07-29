frappe.query_reports["Renewal Pipeline"] = {
	filters: [
		{fieldname: "days", label: __("Within Days"), fieldtype: "Int", default: 60},
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
	],
};
