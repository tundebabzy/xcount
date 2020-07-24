# -*- coding: utf-8 -*-
# Copyright (c) 2018, XLevel Retail Systems Nigeria Ltd and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from erpnext.accounts.general_ledger import process_gl_map
from erpnext.stock import get_warehouse_account_map
from xcount.xcount.doctype.inventory_reconciliation.utils import make_sl_entries
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from frappe import throw, _, _dict, db, msgprint, get_doc, get_list
from frappe.utils import flt
import six


def get_bin_items():
	return get_list("Bin", fields=["name", "item_code", "warehouse", "valuation_rate"])


class InventoryReconciliation(StockReconciliation):
	def set_stock_sheet_reconciled_as(self, value):
		for sheet in self.stock_sheets:
			stock_sheet = get_doc('Stock Sheet', sheet.stock_sheet_name)
			stock_sheet.db_set('reconciled', value)

	def on_submit(self):
		self.set_stock_sheet_reconciled_as(1)
		super(InventoryReconciliation, self).on_submit()

	def on_cancel(self):
		self.set_stock_sheet_reconciled_as(0)
		super(InventoryReconciliation, self).on_cancel()

	def add_uncounted_items_as_zero(self):
		items = [(row.item_code, row.warehouse) for row in self.items]
		bin_items = get_bin_items()
		disabled_items = get_list('Item', filters={'disabled': 1}, fields=['item_code'])

		if self.applicable_warehouse:
			bin_items = [item for item in bin_items if (item.warehouse == self.applicable_warehouse and {'item_code': item.item_code} not in disabled_items)]
		for item in bin_items:
			if (item.item_code, item.warehouse) not in items:
				item.update({'qty': 0})
				self.append('items', item)

	def before_save(self):
		if self.treat_as_zero:
			self.reset_items_from_stock_sheets
			self.add_uncounted_items_as_zero()

	def reset_items_from_stock_sheets(self):
		self.items = []
		for stock_sheet in self.stock_sheets:
			d = frappe.get_doc('Stock Sheet', stock_sheet.name)
			if d.docstatus == 1:
				self.append('items', {
					'barcode': d.barcode,
					'item_code': d.item_code,
					'item_name': d.item_name,
					'qty': d.qty,
					'valuation_rate': d.valuation_rate,
					'warehouse': d.warehouse
				})


	def validate(self):
		self.consolidate_stock_sheet_items()
		super(InventoryReconciliation, self).validate()

	def consolidate_stock_sheet_items(self):
		"""
		This will consolidate all items having the same `item_code` into one
		record. That means if you have a list of records:
		[
			{'item_code': 'test', 'qty': 10'},
			{'item_code': 'test', 'qty': 10'},
			{'item_code': 'test1', 'qty': 100'}
			{'item_code': 'test1', 'qty': 100'}
		],
		it will become:
		[
			{'item_code': 'test', 'qty': 20'},
			{'item_code1': 'test', 'qty': 200'}
		].

		The result will be sorted by `item_code`
		"""
		items = self.items
		if items:
			items.sort(key=lambda i: i.item_code)
			self.items = _consolidate(items)

	def make_sl_entries(self, sl_entries, is_amended=None, allow_negative_stock=False, via_landed_cost_voucher=False):
		"""
		This method shadows `erpnext.stock.stock_ledger.make_sl_entries` because it is
		hard coded to work with on 'Stock Reconciliation` doctype.

		It makes use of a new `make_sl_entries` method that is not tied to any specific doctype
		"""
		try:
			# <= v12
			make_sl_entries(self.doctype, sl_entries, is_amended, allow_negative_stock, via_landed_cost_voucher)
		except TypeError:
			# v13
			make_sl_entries(sl_entries=sl_entries, allow_negative_stock=allow_negative_stock, via_landed_cost_voucher=via_landed_cost_voucher)

	def get_voucher_details(self, default_expense_account, default_cost_center, sle_map):
		if self.doctype == "Inventory Reconciliation":
			return [_dict({"name": voucher_detail_no, "expense_account": default_expense_account,
				"cost_center": default_cost_center}) for voucher_detail_no, sle in sle_map.items()]
		else:
			details = self.get("items")

			if default_expense_account or default_cost_center:
				for d in details:
					if default_expense_account and not d.get("expense_account"):
						d.expense_account = default_expense_account
					if default_cost_center and not d.get("cost_center"):
						d.cost_center = default_cost_center

			return details

	def get_gl_entries(self, warehouse_account=None, default_expense_account=None,
					   default_cost_center=None):
		default_expense_account = self.expense_account
		default_cost_center = self.cost_center

		if not self.cost_center:
			msgprint(_("Please enter Cost Center"), raise_exception=1)

		if not warehouse_account:
			warehouse_account = get_warehouse_account_map()

		sle_map = self.get_stock_ledger_details()
		voucher_details = self.get_voucher_details(default_expense_account, default_cost_center, sle_map)

		gl_list = []
		warehouse_with_no_account = []

		for item_row in voucher_details:
			sle_list = sle_map.get(item_row.name)
			if sle_list:
				for sle in sle_list:
					if warehouse_account.get(sle.warehouse):
						# from warehouse account

						self.check_expense_account(item_row)

						# If the item does not have the allow zero valuation rate flag set
						# and ( valuation rate not mentioned in an incoming entry
						# or incoming entry not found while delivering the item),
						# try to pick valuation rate from previous sle or Item master and update in SLE
						# Otherwise, throw an exception

						if not sle.stock_value_difference and self.doctype != "Inventory Reconciliation" \
							and not item_row.get("allow_zero_valuation_rate"):
							sle = self.update_stock_ledger_entries(sle)

						gl_list.append(self.get_gl_dict({
							"account": warehouse_account[sle.warehouse]["account"],
							"against": item_row.expense_account,
							"cost_center": item_row.cost_center,
							"remarks": self.get("remarks") or "Accounting Entry for Stock",
							"debit": flt(sle.stock_value_difference, 2),
						}, warehouse_account[sle.warehouse]["account_currency"]))

						# to target warehouse / expense account
						gl_list.append(self.get_gl_dict({
							"account": item_row.expense_account,
							"against": warehouse_account[sle.warehouse]["account"],
							"cost_center": item_row.cost_center,
							"remarks": self.get("remarks") or "Accounting Entry for Stock",
							"credit": flt(sle.stock_value_difference, 2),
							"project": item_row.get("project") or self.get("project")
						}))

					elif sle.warehouse not in warehouse_with_no_account:
						warehouse_with_no_account.append(sle.warehouse)

		if warehouse_with_no_account:
			for wh in warehouse_with_no_account:
				if db.get_value("Warehouse", wh, "company"):
					throw(_("Warehouse {0} is not linked to any account, please "
							"mention the account in  the warehouse record or set "
							"default inventory account in company {1}.").format(wh, self.company))

		return process_gl_map(gl_list)


def _add_to_cache(key, value, cache):
	"""
	Populate a dictionary to be used as a cache store
	:param key: string representing the key
	:param value: object
	:param cache: dictionary representing the cache store
	:return: dict
	"""
	cache[key] = value
	return cache


def _consolidate(document_list):
	cache = {}
	doc_list = document_list
	for doc in doc_list:
		key_hash = hash('{0}{1}'.format(doc.item_code, doc.warehouse))
		if not cache.get(key_hash):
			cache = _add_to_cache(key_hash, doc, cache)
		else:
			chosen_doc = cache.get(key_hash)

			chosen_doc.set('qty', flt(chosen_doc.qty) + flt(doc.qty))

	result = list(six.itervalues(cache)) or []

	return result
