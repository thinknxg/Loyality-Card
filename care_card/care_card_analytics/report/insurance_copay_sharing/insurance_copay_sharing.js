frappe.query_reports["Insurance Copay Sharing"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -6)},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
			default: frappe.datetime.get_today()},
		{fieldname: "insurance_company", label: __("Insurer"), fieldtype: "Data"},
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
	],
};
