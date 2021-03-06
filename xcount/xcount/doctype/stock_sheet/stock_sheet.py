# -*- coding: utf-8 -*-
# Copyright (c) 2018, XLevel Retail Systems Nigeria Ltd and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc


class StockSheet(Document):
	pass


@frappe.whitelist()
def make_stock_reconciliation(source_name, target_doc=None, ignore_permisions=False):
	doc = get_mapped_doc(
		'Stock Sheet',
		source_name,
		{
			'Stock Sheet': {
				'doctype': 'Invoice Reconciliation',
				'validation': {
					'docstatus': ['=', 1]
				}
			},
			'Stock Sheet Item': {
				'doctype': 'Inventory Reconciliation Item',
				'field_map': {
					'barcode': 'barcode',
					'item_code': 'item_code',
					'item_name': 'item_name',
					'qty': 'qty',
					'valuation_rate': 'valuation_rate',
					'warehouse': 'warehouse'
				}
			}
		},
		target_doc
	)

	warehouse = frappe.get_value('Stock Sheet', source_name, 'default_warehouse')

	print(doc)

	if doc.get('stock_sheets'):
		for item in doc.stock_sheets:
			if (item.stock_sheet_name == source_name):
				frappe.throw('Stock Sheet - {0} has already been imported.'.format(source_name))

	doc.append(
		'stock_sheets', 
		{
			'stock_sheet_name': source_name,
			'warehouse': warehouse
		}
	)

	return doc
