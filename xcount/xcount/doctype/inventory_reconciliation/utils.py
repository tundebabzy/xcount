"""
A set of classes and modules to help inject some actions and logic into some of
ERPNext's bundled DocTypes like `Stock Ledger Entry`, `Stock Entry`, etc.

Because we don't want to directly modify those doctypes, the goal is to make
our `Inventory Reconciliation` doctype as independent as possible. The problem
is that many of the methods and functions we require have hard coded
references to `Stock Reconciliation`. Therefore, there's quite a lot of
monkey patching.
"""

import json

from erpnext.stock.doctype.bin.bin import Bin
from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry
from erpnext.stock.stock_ledger import update_entries_after, set_as_cancel
from erpnext.stock.utils import get_bin
from frappe import get_doc, throw, _, msgprint, db
from frappe.utils import cint, flt, nowdate


class LedgerEntries(update_entries_after):
	"""
	This subclasses `update_entries_after` so as to override the `process_sle`
	method so as to change the condition requiring `Stock Reconciliation` to
	`Inventory Reconciliation`.
	"""
	def process_sle(self, sle):
		if (sle.serial_no and not self.via_landed_cost_voucher) or not cint(self.allow_negative_stock):
			# validate negative stock for serialized items, fifo valuation
			# or when negative stock is not allowed for moving average
			if not self.validate_negative_stock(sle):
				self.qty_after_transaction += flt(sle.actual_qty)
				return

		if sle.serial_no:
			self.get_serialized_values(sle)
			self.qty_after_transaction += flt(sle.actual_qty)
			self.stock_value = flt(self.qty_after_transaction) * flt(self.valuation_rate)
		else:
			if sle.voucher_type == "Inventory Reconciliation":
				# assert
				self.valuation_rate = sle.valuation_rate
				self.qty_after_transaction = sle.qty_after_transaction
				self.stock_queue = [[self.qty_after_transaction, self.valuation_rate]]
				self.stock_value = flt(self.qty_after_transaction) * flt(self.valuation_rate)
			else:
				if self.valuation_method == "Moving Average":
					self.get_moving_average_values(sle)
					self.qty_after_transaction += flt(sle.actual_qty)
					self.stock_value = flt(self.qty_after_transaction) * flt(self.valuation_rate)
				else:
					self.get_fifo_values(sle)
					self.qty_after_transaction += flt(sle.actual_qty)
					self.stock_value = sum((flt(batch[0]) * flt(batch[1]) for batch in self.stock_queue))

		# rounding as per precision
		self.stock_value = flt(self.stock_value, self.precision)

		stock_value_difference = self.stock_value - self.prev_stock_value
		self.prev_stock_value = self.stock_value

		# update current sle
		sle.qty_after_transaction = self.qty_after_transaction
		sle.valuation_rate = self.valuation_rate
		sle.stock_value = self.stock_value
		sle.stock_queue = json.dumps(self.stock_queue)
		sle.stock_value_difference = stock_value_difference
		sle.doctype="Stock Ledger Entry"
		get_doc(sle).db_update()


def update_bin(args, allow_negative_stock=False, via_landed_cost_voucher=False):
	is_stock_item = db.get_value('Item', args.get("item_code"), 'is_stock_item')
	if is_stock_item:
		bin_ = get_bin(args.get("item_code"), args.get("warehouse"))
		bin_.update_stock_ = update_stock_.__get__(bin_, Bin)
		bin_.update_stock_(args, allow_negative_stock, via_landed_cost_voucher)
		return bin_
	else:
		msgprint(_("Item {0} ignored since it is not a stock item").format(args.get("item_code")))


def update_stock_(self, args, allow_negative_stock=False, via_landed_cost_voucher=False):
	"""
	This is the same as `Bin.update_stock`. It is adjusted to recognise
	`Inventory Reconciliation` and then monkey-patched in `update_bin` as a
	bound method of Bin.
	"""
	self.update_qty(args)

	if args.get("actual_qty") or args.get("voucher_type") == "Inventory Reconciliation":

		if not args.get("posting_date"):
			args["posting_date"] = nowdate()

		# update valuation and qty after transaction for post dated entry
		if args.get("is_cancelled") == "Yes" and via_landed_cost_voucher:
			return
		LedgerEntries({
			"item_code": self.item_code,
			"warehouse": self.warehouse,
			"posting_date": args.get("posting_date"),
			"posting_time": args.get("posting_time"),
			"voucher_no": args.get("voucher_no")
		}, allow_negative_stock=allow_negative_stock, via_landed_cost_voucher=via_landed_cost_voucher)


try:
	from erpnext.stock.stock_ledger import delete_cancelled_entry
	def make_sl_entries(valid_voucher_type, sl_entries, is_amended=None,
					allow_negative_stock=False, via_landed_cost_voucher=False):
		"""
		This makes `Stock Ledger Entry`s
		:param sl_entries: List of frappe._dict representing a `Stock Entry`
		:param valid_voucher_type: Doctype that is valid when making the `Stock Ledger Entry`
		:param is_amended:
		:param allow_negative_stock:
		:param via_landed_cost_voucher:
		"""
		if sl_entries:
			cancel = True if sl_entries[0].get("is_cancelled") == "Yes" else False
			if cancel:
				set_as_cancel(sl_entries[0].get('voucher_no'), sl_entries[0].get('voucher_type'))

			for sle in sl_entries:
				sle_id = None
				if sle.get('is_cancelled') == 'Yes':
					sle['actual_qty'] = -flt(sle['actual_qty'])

				if sle.get("actual_qty") or sle.get("voucher_type") == valid_voucher_type:
					sle_id = make_entry(sle, allow_negative_stock, via_landed_cost_voucher)

				args = sle.copy()
				args.update({
					"sle_id": sle_id,
					"is_amended": is_amended
				})

				update_bin(args, allow_negative_stock, via_landed_cost_voucher)

			if cancel:
				delete_cancelled_entry(sl_entries[0].get('voucher_type'), sl_entries[0].get('voucher_no'))

except ImportError as e:
	# This eill be version 13
	def make_sl_entries(sl_entries, allow_negative_stock=False, via_landed_cost_voucher=False):
		if sl_entries:
			from erpnext.stock.utils import update_bin

			cancel = sl_entries[0].get("is_cancelled")
			if cancel:
				set_as_cancel(sl_entries[0].get('voucher_type'), sl_entries[0].get('voucher_no'))

			for sle in sl_entries:
				sle_id = None
				if via_landed_cost_voucher or cancel:
					sle['posting_date'] = now_datetime().strftime('%Y-%m-%d')
					sle['posting_time'] = now_datetime().strftime('%H:%M:%S.%f')

					if cancel:
						sle['actual_qty'] = -flt(sle.get('actual_qty'), 0)

						if sle['actual_qty'] < 0 and not sle.get('outgoing_rate'):
							sle['outgoing_rate'] = get_incoming_outgoing_rate_for_cancel(sle.item_code,
								sle.voucher_type, sle.voucher_no, sle.voucher_detail_no)
							sle['incoming_rate'] = 0.0

						if sle['actual_qty'] > 0 and not sle.get('incoming_rate'):
							sle['incoming_rate'] = get_incoming_outgoing_rate_for_cancel(sle.item_code,
								sle.voucher_type, sle.voucher_no, sle.voucher_detail_no)
							sle['outgoing_rate'] = 0.0


				if sle.get("actual_qty") or sle.get("voucher_type")=="Stock Reconciliation":
					sle_id = make_entry(sle, allow_negative_stock, via_landed_cost_voucher)

				args = sle.copy()
				args.update({
					"sle_id": sle_id
				})
				update_bin(args, allow_negative_stock, via_landed_cost_voucher)

def make_entry(args, allow_negative_stock=False, via_landed_cost_voucher=False):
	"""
	This substitutes `erpnext.stock.stock_ledger.make_entry` so that we can use
	`XLevelStockLedgerEntry` which recognises `Inventory Reconciliation` rather
	that `Stock Ledger Entry`.
	"""
	args.update({"doctype": "Stock Ledger Entry"})
	sle = XLevelStockLedgerEntry(**args)
	sle.flags.ignore_permissions = 1
	sle.allow_negative_stock = allow_negative_stock
	sle.via_landed_cost_voucher = via_landed_cost_voucher
	sle.insert()
	sle.submit()
	return sle.name


class XLevelStockLedgerEntry(StockLedgerEntry):
	"""
	This class works exactly like `StockLedgerEntry` but we'll use it to
	override the `validate_mandatory` method which specifically gives a visa
	to only `Stock Reconciliation`
	"""
	def validate_mandatory(self):
		mandatory = ['warehouse', 'posting_date', 'voucher_type', 'voucher_no', 'company']
		for k in mandatory:
			if not self.get(k):
				throw(_("{0} is required").format(self.meta.get_label(k)))

		if self.voucher_type != "Inventory Reconciliation" and not self.actual_qty:
			throw(_("Actual Qty is mandatory"))
