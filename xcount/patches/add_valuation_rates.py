import frappe
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import get_stock_balance_for

def execute():
    data = frappe.db.sql(
        'select a.name, a.item_code, a.warehouse, b.stock_count_date, '
        'b.stock_count_time from `tabStock Sheet Item` a join '
        '`tabStock Sheet` b on a.parent = b.name where a.valuation_rate IS NULL'
        )

    for item in data:
        valuation_rate = get_stock_balance_for(item[1], item[2], item[3], item[4])
        if valuation_rate.get('rate'):
            frappe.db.sql(
                'UPDATE `tabStock Sheet Item` '
                'SET valuation_rate = %s '
                'WHERE name = %s', (valuation_rate['rate'], item[0])
            )
