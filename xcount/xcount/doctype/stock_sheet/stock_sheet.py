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

	doc.append('stock_sheets', {'stock_sheet_name': source_name})

	return doc
