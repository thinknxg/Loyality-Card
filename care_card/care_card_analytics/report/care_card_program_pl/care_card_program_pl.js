frappe.query_reports["Care Card Program PL"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
			default: frappe.datetime.get_today()},
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
	],
};
