// Copyright (c) 2018, XLevel Retail Systems Nigeria Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Sheet', {
	refresh: function(frm) {
		if(frm.doc.docstatus < 1) {
			frm.add_custom_button(__("Items"), function() {
				frm.events.get_items(frm);
			});
		}

		frm.set_value('counted_by', frappe.session.user);
	},

	get_items: function(frm) {
		frappe.prompt({label:"Warehouse", fieldtype:"Link", options:"Warehouse", reqd: 1},
			function(data) {
				frappe.call({
					method:"erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_items",
					args: {
						warehouse: data.warehouse,
						posting_date: frm.doc.stock_count_date,
						posting_time: frm.doc.stock_count_time
					},
					callback: function(r) {
						if (r.message) {
							var items = [];
							frm.clear_table("items");
							for(var i=0; i< r.message.length; i++) {
								var d = frm.add_child("items");
								$.extend(d, r.message[i]);
								if(!d.qty) d.qty = null;
							}
							frm.refresh_field("items");
						}
						else {
							frappe.show_alert(`No items in '${data.warehouse}'`);
						}
					}
				});
			}
		, __("Get Items"), __("Update"));
	},

	onload: function(frm) {
		frm.add_fetch("item_code", "item_name", "item_name");

		if (frm.doc.company) {
			erpnext.queries.setup_queries(frm, "Warehouse", function() {
				return erpnext.queries.warehouse(frm.doc);
			});
		}
	},

	set_item_code: function(doc, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if (d.barcode) {
			frappe.call({
				method: "erpnext.stock.get_item_details.get_item_code",
				args: {"barcode": d.barcode },
				callback: function(r) {
					if (!r.exe){
						frappe.model.set_value(cdt, cdn, "item_code", r.message);
					}
				}
			});
		}
	},

	set_expected_qty: function(frm, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if(d.item_code && d.warehouse) {
			frappe.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.stock_count_date,
					posting_time: frm.doc.stock_count_time
				},
				callback: function(r) {
					frappe.model.set_value(cdt, cdn, "expected_qty", r.message.qty);
				}
			});
		}
	},

	default_warehouse: function(frm) {
		$.each(frm.doc.items || [], function(i, d) {
			if(!d.warehouse) d.warehouse = frm.doc.default_warehouse;
		});
		refresh_field("items");
	},

	set_row_default_warehouse: function(frm, cdt, cdn) {
		if (frm.doc.default_warehouse) {
			const d = frappe.model.get_doc(cdt, cdn);
			frappe.model.set_value(cdt, cdn, 'warehouse', frm.doc.default_warehouse);
		}
		frappe.model.set_value(cdt, cdn, 'warehouse', frm.doc.default_warehouse);
	},

	set_default_qty: function(frm, cdt, cdn) {
		const doc = frappe.model.get_doc(cdt, cdn);
		if (!flt(doc.qty)) {
			frappe.model.set_value(cdt, cdn, 'qty', 1);
		}
	}
});

frappe.ui.form.on('Stock Sheet Item', {
	barcode: function(frm, cdt, cdn) {
		frm.events.set_item_code(frm, cdt, cdn);
	},

	warehouse: function(frm, cdt, cdn) {
		frm.events.set_expected_qty(frm, cdt, cdn);
	},

	item_code: function(frm, cdt, cdn) {
		frm.events.set_row_default_warehouse(frm, cdt, cdn);
		frm.events.set_default_qty(frm, cdt, cdn);
		frm.events.set_expected_qty(frm, cdt, cdn);
	},
});
