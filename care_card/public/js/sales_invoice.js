// Care Card bindings for Sales Invoice / POS Invoice.
["Sales Invoice", "POS Invoice"].forEach(function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (!frm.doc.care_card) {
				frm.add_custom_button(__("Look up Care Card"), () => care_card_lookup(frm),
					__("Care Card"));
				return;
			}
			frm.add_custom_button(__("Explain discounts"), () => explain(frm), __("Care Card"));
			frm.add_custom_button(__("Remove card"), () => {
				frm.set_value("care_card", null);
				frm.set_value("care_card_beneficiary", null);
			}, __("Care Card"));

			if (frm.doc.care_card_status) {
				const eligible = frm.doc.care_card_status === __("Eligible");
				frm.dashboard.add_indicator(
					`${frm.doc.care_card_tier || __("Care Card")}: ${frm.doc.care_card_status}`,
					eligible ? "green" : "orange");
			}
		},

		care_card(frm) {
			if (!frm.doc.care_card) {
				frm.set_value("care_card_beneficiary", null);
				return;
			}
			frappe.call({
				method: "care_card.api.desk.card_detail",
				args: {card: frm.doc.care_card},
				callback(r) {
					if (!r.message) return;
					const detail = r.message;
					if (!detail.eligible) {
						frappe.msgprint({
							title: __("Card not eligible"),
							indicator: "orange",
							message: detail.reason || __("This card cannot be used today."),
						});
					}
					choose_beneficiary(frm, detail);
				},
			});
		},
	});
});

function choose_beneficiary(frm, detail) {
	const people = detail.beneficiaries || [];
	if (people.length <= 1) {
		frm.set_value("care_card_beneficiary", detail.card_number);
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Who is being treated?"),
		fields: [{
			fieldtype: "Select", fieldname: "beneficiary", reqd: 1,
			label: __("Beneficiary"),
			options: people.map((p) => `${p.code} — ${p.name} (${p.relationship})`),
			default: `${people[0].code} — ${people[0].name} (${people[0].relationship})`,
		}],
		primary_action_label: __("Use this person"),
		primary_action(values) {
			frm.set_value("care_card_beneficiary", values.beneficiary.split(" — ")[0]);
			dialog.hide();
			frm.save();
		},
	});
	dialog.show();
}

function care_card_lookup(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Look up Care Card"),
		fields: [
			{fieldtype: "Data", fieldname: "query", reqd: 1,
				label: __("Card number, mobile, civil ID or name"),
				description: __("Scan the card barcode or type any part of the member's details.")},
			{fieldtype: "HTML", fieldname: "results"},
		],
		primary_action_label: __("Search"),
		primary_action(values) {
			frappe.call({
				method: "care_card.api.desk.search",
				args: {query: values.query},
				callback(r) {
					const rows = r.message || [];
					if (!rows.length) {
						dialog.fields_dict.results.$wrapper.html(
							`<p>${__("No card matches that. Check the number or sell a new card.")}</p>`);
						return;
					}
					const html = rows.map((row) => `
						<div class="cc-result" data-card="${row.name}"
							style="padding:8px 0;border-bottom:1px solid var(--border-color);cursor:pointer">
							<b>${frappe.utils.escape_html(row.member_name)}</b> ·
							${frappe.utils.escape_html(row.card_number || "")} ·
							${frappe.utils.escape_html(row.tier || "")} ·
							${frappe.utils.escape_html(row.status || "")}
						</div>`).join("");
					const $wrapper = dialog.fields_dict.results.$wrapper;
					$wrapper.html(html);
					$wrapper.find(".cc-result").on("click", function () {
						frm.set_value("care_card", $(this).data("card"));
						dialog.hide();
					});
				},
			});
		},
	});
	dialog.show();
}

function explain(frm) {
	const lines = (frm.doc.items || []).map((row) => ({
		item_code: row.item_code,
		item_name: row.item_name,
		item_group: row.item_group,
		brand: row.brand,
		qty: row.qty,
		rate: row.price_list_rate || row.rate,
		amount: flt(row.qty) * flt(row.price_list_rate || row.rate),
		is_insured: row.cc_is_insured,
		copay_percent: row.cc_copay_percent,
		copay_amount: row.cc_copay_amount,
		existing_discount_percent: row.cc_existing_discount_percent,
		insurance_company: frm.doc.cc_insurance_company,
		insurance_plan: frm.doc.cc_insurance_plan,
	}));
	frappe.call({
		method: "care_card.api.desk.price_basket",
		args: {
			card: frm.doc.care_card,
			lines: lines,
			beneficiary_code: frm.doc.care_card_beneficiary,
			location: frm.doc.care_card_location,
		},
		callback(r) {
			if (r.message) care_card.explanation_dialog(r.message);
		},
	});
}
