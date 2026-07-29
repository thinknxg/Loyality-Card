frappe.query_reports["Channel and Agent Performance"] = {
	filters: [
		{fieldname: "from_date", label: __("From Date"), fieldtype: "Date"},
		{fieldname: "to_date", label: __("To Date"), fieldtype: "Date"},
		{fieldname: "by_agent", label: __("Group by Agent"), fieldtype: "Check", default: 0},
	],
};
