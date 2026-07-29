frappe.query_reports["Care Card Register"] = {
	filters: [
		{fieldname: "from_date", label: __("Activated From"), fieldtype: "Date"},
		{fieldname: "to_date", label: __("Activated To"), fieldtype: "Date"},
		{fieldname: "tier", label: __("Tier"), fieldtype: "Link", options: "Care Card Tier"},
		{fieldname: "status", label: __("Status"), fieldtype: "Select",
			options: ["", "Draft", "Pending Payment", "Active", "Expired", "Suspended", "Cancelled"]},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "utilization_ratio" && data) {
			const colour = data.utilization_ratio >= 100 ? "red"
				: data.utilization_ratio >= 60 ? "orange" : "green";
			value = `<span style="color:var(--text-on-light-${colour}, ${colour})">${value}</span>`;
		}
		return value;
	},
};
