frappe.query_reports["Visit and Dependent Usage Log"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
			default: frappe.datetime.get_today()},
		{fieldname: "card", label: __("Card"), fieldtype: "Link", options: "Care Card"},
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
		{fieldname: "location", label: __("Location"), fieldtype: "Link",
			options: "Care Participating Location"},
	],
};
