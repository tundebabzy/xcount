// Copyright (c) 2018, XLevel Retail Systems Nigeria Ltd and contributors
// For license information, please see license.txt

frappe.provide('erpnext.stock');

frappe.ui.form.on('Inventory Reconciliation', {
	onload: function(frm) {
		frm.add_fetch("item_code", "item_name", "item_name");

		// end of life
		frm.set_query("item_code", "items", function(doc, cdt, cdn) {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters:{
					"is_stock_item": 1,
					"has_serial_no": 0
				}
			}
		});

		if (frm.doc.company) {
			erpnext.queries.setup_queries(frm, "Warehouse", function() {
				return erpnext.queries.warehouse(frm.doc);
			});
		}

		if (!frm.doc.expense_account) {
			frm.trigger("set_expense_account");
		}
	},

	refresh: function(frm) {
		if(frm.doc.docstatus < 1) {
			frm.add_custom_button(__("Stock Count Sheets"), function() {
				frm.events.get_stock_count_sheets(frm);
			});
		}

		if(frm.doc.company) {
			frm.trigger("toggle_display_account_head");
		}
	},

	// treat_as_zero: function(frm) {
	// 	if (!frm.doc.treat_as_zero) {
	// 		frm.set_value('applicable_warehouse', '');
	// 	}
	// },
	applicable_warehouse: function(frm) {
		frm.clear_table('items');
		frm.clear_table('stock_sheets');
		// frm.events.reset_items_table(frm);
		// frm.events.reset_stock_sheets_table(frm);
		// if (!frm.doc.items.length) {
		// 	frm.add_child('items');
		// }
		frm.refresh_field('items');
		frm.refresh_field('stock_sheets');
	},

	get_stock_count_sheets: function(frm) {
		const filters = {
			docstatus: 1,
			reconciled: 0,
			company: frm.doc.company
		};
		if (frm.doc.applicable_warehouse) {
			filters.default_warehouse = frm.doc.applicable_warehouse
		}
		erpnext.utils.map_current_doc({
			method: 'xcount.xcount.doctype.stock_sheet.stock_sheet.make_stock_reconciliation',
			source_doctype: "Stock Sheet",
			target: me.frm,
			date_field: 'stock_count_date',
			setters: {},
			get_query_filters: filters
		})
	},

	get_items: function(frm) {
		frappe.prompt({label:"Warehouse", fieldtype:"Link", options:"Warehouse", reqd: 1},
			function(data) {
				frappe.call({
					method:"erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_items",
					args: {
						warehouse: data.warehouse,
						posting_date: frm.doc.posting_date,
						posting_time: frm.doc.posting_time
					},
					callback: function(r) {
						frm.clear_table("items");
						for(var i=0; i< r.message.length; i++) {
							var d = frm.add_child("items");
							$.extend(d, r.message[i]);
							if(!d.qty) d.qty = null;
							if(!d.valuation_rate) d.valuation_rate = null;
						}
						frm.refresh_field("items");
					}
				});
			}
		, __("Get Items"), __("Update"));
	},

	reset_items_table: function(frm) {
		if (frm.doc.applicable_warehouse) {
			const {applicable_warehouse, items} = frm.doc;
			frm.clear_table('items');
			if (items) {
				items.forEach(item => {
					if (item.warehouse === applicable_warehouse) {
						const d = frm.add_child('items', item);
					}
				});
			}
		}
	},

	reset_stock_sheets_table(frm) {
		if (frm.doc.applicable_warehouse) {
			const {applicable_warehouse, stock_sheets} = frm.doc;
			frm.clear_table('stock_sheets');
			if (stock_sheets) {
				stock_sheets.forEach(item => {
					if (item.warehouse === applicable_warehouse) {
						const d = frm.add_child('stock_sheets');
						$.extend(d, item);
					}
				});
			}
		}
	},

	set_valuation_rate_and_qty: function(frm, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if(d.item_code && d.warehouse) {
			frappe.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time
				},
				callback: function(r) {
					frappe.model.set_value(cdt, cdn, "qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "current_valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_amount", r.message.rate * r.message.qty);
					frappe.model.set_value(cdt, cdn, "amount", r.message.rate * r.message.qty);

				}
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

	set_amount_quantity: function(doc, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if (d.qty & d.valuation_rate) {
			frappe.model.set_value(cdt, cdn, "amount", flt(d.qty) * flt(d.valuation_rate));
			frappe.model.set_value(cdt, cdn, "quantity_difference", flt(d.qty) - flt(d.current_qty));
			frappe.model.set_value(cdt, cdn, "amount_difference", flt(d.amount) - flt(d.current_amount));
		}
	},

	company: function(frm) {
		frm.trigger("toggle_display_account_head");
	},

	toggle_display_account_head: function(frm) {
		frm.toggle_display(['expense_account', 'cost_center'],
			erpnext.is_perpetual_inventory_enabled(frm.doc.company));
	},

	purpose: function(frm) {
		frm.trigger("set_expense_account");
	},

	set_expense_account: function(frm) {
		if (frm.doc.company && erpnext.is_perpetual_inventory_enabled(frm.doc.company)) {
			return frm.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_difference_account",
				args: {
					"purpose": frm.doc.purpose,
					"company": frm.doc.company
				},
				callback: function(r) {
					if (!r.exc) {
						frm.set_value("expense_account", r.message);
					}
				}
			});
		}
	}
});

frappe.ui.form.on("Inventory Reconciliation Item", {
	barcode: function(frm, cdt, cdn) {
		frm.events.set_item_code(frm, cdt, cdn);
	},
	warehouse: function(frm, cdt, cdn) {
		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},
	item_code: function(frm, cdt, cdn) {
		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},
	qty: function(frm, cdt, cdn) {
		frm.events.set_amount_quantity(frm, cdt, cdn);
	},
	valuation_rate: function(frm, cdt, cdn) {
		frm.events.set_amount_quantity(frm, cdt, cdn);
	}

});

erpnext.stock.InventoryReconciliation = erpnext.stock.StockController.extend({
	setup: function() {
		var me = this;

		this.setup_posting_date_time_check();

		if (me.frm.doc.company && erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
			this.frm.add_fetch("company", "cost_center", "cost_center");
		}
		this.frm.fields_dict["expense_account"].get_query = function() {
			if(erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
				return {
					"filters": {
						'company': me.frm.doc.company,
						"is_group": 0
					}
				}
			}
		}
		this.frm.fields_dict["cost_center"].get_query = function() {
			if(erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
				return {
					"filters": {
						'company': me.frm.doc.company,
						"is_group": 0
					}
				}
			}
		}
	},

	refresh: function() {
		if(this.frm.doc.docstatus==1) {
			this.show_stock_ledger();
			if (erpnext.is_perpetual_inventory_enabled(this.frm.doc.company)) {
				this.show_general_ledger();
			}
		}
	}
});

cur_frm.cscript = new erpnext.stock.InventoryReconciliation({frm: cur_frm});
