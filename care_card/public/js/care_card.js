// Care Card — shared desk helpers.
frappe.provide("care_card");

care_card.format_money = function (value) {
	return format_currency(flt(value), frappe.defaults.get_default("currency") || "OMR", 3);
};

care_card.explanation_dialog = function (result) {
	const rows = (result.lines || []).map(function (line) {
		const granted = flt(line.discount_amount) + flt(line.copay_shared);
		return `<tr>
			<td>${frappe.utils.escape_html(line.item_name || line.item_code || "")}</td>
			<td>${frappe.utils.escape_html(line.benefit_category || "—")}</td>
			<td class="num">${care_card.format_money(line.gross_amount)}</td>
			<td class="num">${care_card.format_money(granted)}</td>
			<td class="cc-explanation-why">${frappe.utils.escape_html(line.explanation || "")}</td>
		</tr>`;
	}).join("");

	const totals = result.totals || {};
	const head = result.eligible
		? `<p>${__("Card")} <b>${frappe.utils.escape_html(result.card_number || "")}</b> · ${__("Tier")}
			<b>${frappe.utils.escape_html(result.tier || "")}</b> · ${__("Beneficiary")}
			<b>${frappe.utils.escape_html(result.beneficiary_name || "")}</b></p>`
		: `<p class="text-danger">${frappe.utils.escape_html(result.reason || __("Card not eligible"))}</p>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Card Discount Explanation"),
		size: "large",
		fields: [{fieldtype: "HTML", fieldname: "body"}],
	});
	dialog.fields_dict.body.$wrapper.html(`
		${head}
		<table class="cc-explanation-table">
			<thead><tr>
				<th>${__("Item")}</th><th>${__("Category")}</th>
				<th class="num">${__("Gross")}</th><th class="num">${__("Granted")}</th>
				<th>${__("Why")}</th>
			</tr></thead>
			<tbody>${rows || `<tr><td colspan="5">${__("Nothing to price")}</td></tr>`}</tbody>
		</table>
		<p style="margin-top:12px">
			${__("Discount")}: <b>${care_card.format_money(totals.discount)}</b> ·
			${__("Co-pay shared")}: <b>${care_card.format_money(totals.copay_shared)}</b> ·
			${__("Net")}: <b>${care_card.format_money(totals.net)}</b>
		</p>
	`);
	dialog.show();
};
