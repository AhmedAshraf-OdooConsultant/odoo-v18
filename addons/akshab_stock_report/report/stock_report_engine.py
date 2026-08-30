# -*- coding: utf-8 -*-
"""
Akshab inventory reports – shared data engine.

One engine feeds the four reports of the module (comprehensive status report,
aging report, turnover report, item-status report).  It builds a plain Python
dictionary consumed by the QWeb (PDF) templates and the XLSX writers.  All
heavy lifting is done with a handful of aggregated SQL queries on stock.quant /
stock.move.line / stock.valuation.layer so the reports stay fast on large
databases.

Methodology (documented in the reports themselves):
* On-hand quantities: stock.quant for "now"; rebuilt from done stock moves for a
  past "as-of" date (same logic as Odoo's ``to_date`` context).  Scope = internal
  locations of the selected warehouses / locations.
* Aging: FIFO assumption – the quantity on hand in a branch is attributed to the
  most recent receipts into that branch, newest first.  Returns are applied to
  the ORIGINAL move they are linked to (see ``_sql_receipts``).
* Negative stock: a negative branch balance (sales recorded without enough
  stock) is never aged nor valued.  A receipt that arrives after a negative
  balance first covers that balance; only the remainder is aged from the
  receipt date.
* Sales velocity: net customer deliveries (deliveries − returns, returns netted
  at the original sale date) from stock moves, so POS and sales-order
  deliveries are treated alike.
* Valuation: average cost from stock valuation layers (or the product's
  standard cost) × quantity on hand.
* Turnover: COGS of the period (actual cost of goods delivered from the
  valuation layers, or quantity × unit cost) ÷ average inventory
  ((opening + closing) / 2); inventory days = period days ÷ turnover;
  stock coverage = quantity on hand ÷ average daily sales of the coverage window.
"""
import math
import re
from collections import defaultdict
from datetime import timedelta

from odoo import fields
from odoo.tools import float_round

ARABIC_INDIC = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')

STATUS_LABELS = {
    'active': 'نشط',
    'slow': 'بطيء الحركة (فائض)',
    'stagnant': 'راكد',
    'new': 'جديد',
    'out': 'نافد وله طلب',
}
STATUS_ORDER = ['active', 'slow', 'stagnant', 'new']

ACTION_LABELS = {
    'liquidate': 'تصفية فورية',
    'discount_high': 'خصم قوي / عرض حزمة',
    'discount': 'عرض ترويجي / خصم',
    'transfer': 'إعادة توزيع بين الفروع',
    'stop_buy': 'إيقاف الشراء + عرض محدود',
    'reorder': 'إعادة طلب',
    'reorder_urgent': 'إعادة طلب عاجل',
    'watch': 'متابعة',
    'keep': 'مستوى مناسب',
}

COST_BASIS_LABELS = {
    'svl': 'متوسط التكلفة من طبقات التقييم',
    'standard': 'التكلفة المسجلة على الصنف',
}
COGS_BASIS_LABELS = {
    'svl': 'تكلفة البضاعة المباعة الفعلية من طبقات التقييم',
    'unit_cost': 'كمية المبيعات × متوسط التكلفة',
}


def fmt_money(value, digits=2):
    """1234.5 -> '1,234.50' (never returns '-0.00')."""
    if value is None:
        return '-'
    value = float(value)
    if abs(value) < 0.005:
        value = 0.0
    return '{:,.{d}f}'.format(value, d=digits)


def fmt_qty(value):
    """Quantities: integers without decimals, otherwise two decimals (like the sales report)."""
    if value is None:
        return '-'
    value = float(value)
    if abs(value - round(value)) < 0.005:
        return '{:,.0f}'.format(round(value))
    return '{:,.2f}'.format(value)


def fmt_pct(value, digits=1):
    if value is None:
        return '-'
    return '{:.{d}f}%'.format(float(value), d=digits)


def fmt_int(value):
    if value is None:
        return '-'
    return '{:,.0f}'.format(float(value))


def fmt_ratio(value, digits=2):
    if value is None:
        return '-'
    return '{:,.{d}f}'.format(float(value), d=digits)


def to_arabic_indic(text):
    return str(text).translate(ARABIC_INDIC)


def ar_count(n, singular, dual, plural, accusative):
    """Arabic counted-noun agreement: 1 -> 'singular واحد', 2 -> dual, 3-10 -> 'N plural', 11+ -> 'N accusative'."""
    n = int(round(n or 0))
    if n == 0:
        return 'لا %s' % plural
    if n == 1:
        return '%s واحد' % singular
    if n == 2:
        return dual
    if 3 <= n <= 10:
        return '%s %s' % (fmt_int(n), plural)
    return '%s %s' % (fmt_int(n), accusative)


def ar_items(n):
    return ar_count(n, 'صنف', 'صنفان', 'أصناف', 'صنفاً')


def ar_days(n):
    return ar_count(n, 'يوم', 'يومان', 'أيام', 'يوماً')


class ReportOptions:
    """Attribute bag with the defaults shared by all report wizards."""

    DEFAULTS = {
        'company': None,
        'date_to': None,            # datetime (UTC naive); None -> now
        'date_from': None,          # datetime; None -> date_to - sales_days
        'warehouse_ids': None,      # stock.warehouse recordset (empty -> all)
        'location_ids': None,       # stock.location recordset (empty -> all internal)
        'categ_ids': None,
        'product_ids': None,
        'sales_days': 90,
        'coverage_days': 0,         # 0 -> same window as the sales analysis
        'stagnant_days': 90,
        'new_days': 30,
        'slow_cover_days': 180,
        'reorder_cover_days': 15,
        'liquidation_discount': 30.0,
        'cost_basis': 'svl',
        'cogs_basis': 'svl',
        'buckets': (30, 60, 90, 180, 365),
        'aging_scope': 'scope',     # 'scope': age since entering the SELECTED scope (whole company
                                    #   when no warehouse/location filter) - internal transfers
                                    #   inside the scope never count as receipts.
                                    # 'branch': age since entering the branch (a transfer between
                                    #   branches starts a new age in the receiving branch).
        'old_days': 180,
        'top_n': 10,                # size of the most / least turning product lists
        'max_lines': 50,
        'show_active': True,
        'show_out_of_stock': True,
        'show_category_aging': True,
    }

    def __init__(self, **kw):
        for key, val in self.DEFAULTS.items():
            setattr(self, key, kw.get(key, val))
        unknown = set(kw) - set(self.DEFAULTS)
        if unknown:
            raise ValueError('Unknown report options: %s' % ', '.join(sorted(unknown)))


class StockReportEngine:

    def __init__(self, record, options):
        """``record`` is any Odoo record (used for env / user timezone), ``options`` a ReportOptions."""
        self.rec = record
        self.o = options
        self.env = record.env
        self.cr = record.env.cr
        self.company = options.company or record.env.company
        self.currency = self.company.currency_id
        self.now = fields.Datetime.now()
        self.date_to = fields.Datetime.to_datetime(options.date_to) if options.date_to else self.now
        if self.date_to > self.now:
            self.date_to = self.now   # a future date makes no sense for stock: use the present
        # "now" mode when the as-of datetime is (almost) the present
        self.is_now = self.date_to >= self.now - timedelta(minutes=30)
        if options.date_from:
            self.sales_from = fields.Datetime.to_datetime(options.date_from)
            if self.sales_from >= self.date_to:
                self.sales_from = self.date_to - timedelta(days=1)
        else:
            self.sales_from = self.date_to - timedelta(days=max(1, int(options.sales_days or 90)))
        self.period_days = max(1, int(round((self.date_to - self.sales_from).total_seconds() / 86400.0)))
        cov = int(options.coverage_days or 0)
        self.cov_from = (self.date_to - timedelta(days=cov)) if cov > 0 else self.sales_from
        self.cov_days = max(1, int(round((self.date_to - self.cov_from).total_seconds() / 86400.0)))
        self.buckets = [int(b) for b in options.buckets]
        self.n_buckets = len(self.buckets) + 1
        self.bucket_labels = self._bucket_labels()
        self.old_days = int(options.old_days or (self.buckets[3] if len(self.buckets) > 3 else self.buckets[-1]))
        self.old_from = sum(1 for b in self.buckets if b <= self.old_days)   # first "old" bucket index
        self.discount = max(0.0, min(99.0, float(options.liquidation_discount or 0.0))) / 100.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bucket_labels(self):
        b = self.buckets
        labels = ['0 – %d يوم' % b[0]]
        for i in range(1, len(b)):
            labels.append('%d – %d يوم' % (b[i - 1] + 1, b[i]))
        labels.append('أكثر من %d يوم' % b[-1])
        return labels

    def _bucket_index(self, age_days):
        for i, limit in enumerate(self.buckets):
            if age_days <= limit:
                return i
        return len(self.buckets)

    def _days(self, dt):
        """Whole days between a datetime and the as-of date (never negative)."""
        if not dt:
            return None
        dt = fields.Datetime.to_datetime(dt)
        return max(0, int((self.date_to - dt).total_seconds() // 86400))

    def _fmt_date(self, dt):
        if not dt:
            return '-'
        dt = fields.Datetime.to_datetime(dt)
        return fields.Datetime.context_timestamp(self.rec, dt).strftime('%Y-%m-%d')

    def _fmt_datetime(self, dt):
        if not dt:
            return '-'
        dt = fields.Datetime.to_datetime(dt)
        return fields.Datetime.context_timestamp(self.rec, dt).strftime('%Y-%m-%d %H:%M')

    @property
    def currency_symbol(self):
        if self.currency.name == 'SAR':
            return 'ر.س'
        return self.currency.symbol or self.currency.name

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------
    def _load_scope(self):
        o = self.o
        Warehouse = self.env['stock.warehouse']
        warehouses = o.warehouse_ids or Warehouse.search([('company_id', '=', self.company.id)])
        warehouses = warehouses.sorted(lambda x: (x.sequence, x.id)) if 'sequence' in Warehouse._fields else warehouses
        self.warehouses = warehouses
        self.wh_names = {wh.id: wh.name for wh in warehouses}
        self.wh_names[0] = 'بدون مستودع'

        loc_domain = [('usage', '=', 'internal'), ('company_id', '=', self.company.id)]
        if o.warehouse_ids:
            loc_domain.append(('warehouse_id', 'in', warehouses.ids))
        if o.location_ids:
            loc_domain.append(('id', 'child_of', o.location_ids.ids))
        locations = self.env['stock.location'].with_context(active_test=False).search(loc_domain)
        self.location_ids = locations.ids
        self.location_names = locations.mapped('complete_name')
        if o.location_ids:
            # only the warehouses that actually own a location in scope
            in_scope = set(locations.mapped('warehouse_id').ids)
            self.warehouses = warehouses.filtered(lambda w: w.id in in_scope)
            self.wh_names = {wh.id: wh.name for wh in self.warehouses}
            self.wh_names[0] = 'بدون مستودع'

        prod_domain = [('is_storable', '=', True), ('company_id', 'in', [self.company.id, False])]
        if o.categ_ids:
            prod_domain.append(('categ_id', 'child_of', o.categ_ids.ids))
        if o.product_ids:
            prod_domain.append(('id', 'in', o.product_ids.ids))
        self.products = self.env['product.product'].with_context(active_test=False).search(prod_domain)
        self.product_ids = self.products.ids

    # ------------------------------------------------------------------
    # SQL data
    # ------------------------------------------------------------------
    def _sql_on_hand(self, at_date=None):
        """{(product_id, wh_id): qty} as of ``at_date`` (default: the report date)."""
        res = defaultdict(float)
        if not self.location_ids or not self.product_ids:
            return res
        use_quants = at_date is None and self.is_now
        at_date = at_date or self.date_to
        if use_quants:
            self.cr.execute("""
                SELECT q.product_id, COALESCE(l.warehouse_id, 0), SUM(q.quantity)
                  FROM stock_quant q
                  JOIN stock_location l ON l.id = q.location_id
                 WHERE q.location_id IN %s AND q.product_id IN %s
              GROUP BY q.product_id, COALESCE(l.warehouse_id, 0)
            """, (tuple(self.location_ids), tuple(self.product_ids)))
        else:
            self.cr.execute("""
                SELECT product_id, wh, SUM(qty) FROM (
                    SELECT ml.product_id, COALESCE(l.warehouse_id, 0) AS wh, ml.quantity_product_uom AS qty
                      FROM stock_move_line ml
                      JOIN stock_move m ON m.id = ml.move_id
                      JOIN stock_location l ON l.id = ml.location_dest_id
                     WHERE m.state = 'done' AND m.date <= %s
                       AND ml.location_dest_id IN %s AND ml.product_id IN %s
                    UNION ALL
                    SELECT ml.product_id, COALESCE(l.warehouse_id, 0) AS wh, -ml.quantity_product_uom AS qty
                      FROM stock_move_line ml
                      JOIN stock_move m ON m.id = ml.move_id
                      JOIN stock_location l ON l.id = ml.location_id
                     WHERE m.state = 'done' AND m.date <= %s
                       AND ml.location_id IN %s AND ml.product_id IN %s
                ) t GROUP BY product_id, wh
            """, (at_date, tuple(self.location_ids), tuple(self.product_ids),
                  at_date, tuple(self.location_ids), tuple(self.product_ids)))
        for product_id, wh, qty in self.cr.fetchall():
            res[(product_id, wh)] += float(qty or 0.0)
        return res

    def _sql_receipts(self, product_ids):
        """Receipts into the aging perimeter, newest first, with returns applied to the
        ORIGINAL move they are linked to.

        The perimeter follows ``aging_scope``:

        * ``scope`` (default): one perimeter = ALL the selected internal locations (the whole
          company when no warehouse/location filter).  Only stock entering the perimeter from
          outside it (supplier, inventory adjustment, production, a location outside the
          selection) is a receipt — internal transfers INSIDE the perimeter never reset the
          age.  Entries are keyed (product_id, 0).
        * ``branch``: one perimeter per warehouse — a transfer between branches is a receipt
          in the receiving branch.  Entries are keyed (product_id, warehouse_id).

        Returns rules (both modes):

        * an outbound move that is a return of a receipt (``origin_returned_move_id`` set –
          e.g. a purchase return) reduces the quantity of that original receipt, at the
          original receipt date – it is never treated as a normal issue;
        * an inbound move that is a return of a delivery / transfer (customer return –
          linked or not, e.g. POS refunds – or a branch return) is NOT a new receipt: the
          goods come back with their original age (the on-hand quantity is simply
          attributed to the older receipts);
        * a return of a return (goods sent back by the supplier again) restores the
          original receipt;
        * an unlinked return to a supplier reduces the latest receipts before it (LIFO).

        Returns {(product_id, key): [entry, ...]} with entry = {'date', 'qty', 'move_id'}.
        """
        lines = defaultdict(list)
        if not self.location_ids or not product_ids:
            return lines
        scope = self.o.aging_scope != 'branch'
        loc = tuple(self.location_ids)
        if scope:
            in_wh, out_wh = '0', '0'
            in_outside = 'AND ml.location_id NOT IN %s'
            out_outside = 'AND ml.location_dest_id NOT IN %s'
            params = (self.date_to, loc, tuple(product_ids), loc)
        else:
            in_wh, out_wh = 'COALESCE(ld.warehouse_id, 0)', 'COALESCE(ls.warehouse_id, 0)'
            in_outside = "AND (ls.usage <> 'internal' OR COALESCE(ls.warehouse_id, 0) <> COALESCE(ld.warehouse_id, 0))"
            out_outside = "AND (ld.usage <> 'internal' OR COALESCE(ld.warehouse_id, 0) <> COALESCE(ls.warehouse_id, 0))"
            params = (self.date_to, loc, tuple(product_ids))
        # 1) inbound lines into the perimeter from outside it
        self.cr.execute("""
            SELECT ml.product_id, %s, m.id, m.date, ml.quantity_product_uom,
                   m.origin_returned_move_id, o.origin_returned_move_id
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              LEFT JOIN stock_move o ON o.id = m.origin_returned_move_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
              JOIN stock_location ls ON ls.id = ml.location_id
             WHERE m.state = 'done' AND m.date <= %%s
               AND ml.location_dest_id IN %%s
               AND ml.product_id IN %%s
               AND ml.quantity_product_uom > 0
               AND ls.usage <> 'customer'
               %s
          ORDER BY m.date DESC, m.id DESC
        """ % (in_wh, in_outside), params)
        entries = {}      # (move_id, wh) -> entry
        restores = []     # returns of returns -> restore the root receipt
        for product_id, wh, move_id, date, qty, origin_id, root_id in self.cr.fetchall():
            qty = float(qty)
            if origin_id and root_id:
                restores.append((product_id, wh, root_id, qty, date))
                continue
            if origin_id:
                # branch return: goods come back with their original age
                continue
            key = (move_id, wh)
            entry = entries.get(key)
            if entry is None:
                entry = {'move_id': move_id, 'date': date, 'qty': 0.0, 'orig': 0.0}
                entries[key] = entry
                lines[(product_id, wh)].append(entry)
            entry['qty'] += qty
            entry['orig'] += qty
        for product_id, wh, root_id, qty, date in restores:
            entry = entries.get((root_id, wh))
            if entry is not None:
                entry['qty'] = min(entry['orig'], entry['qty'] + qty)
            else:
                lines[(product_id, wh)].append({'move_id': None, 'date': date, 'qty': qty, 'orig': qty})
                lines[(product_id, wh)].sort(key=lambda e: e['date'], reverse=True)

        # 2) outbound returns: linked ones reduce their original receipt; unlinked returns to a
        #    supplier reduce the latest receipts before them (LIFO)
        self.cr.execute("""
            SELECT ml.product_id, %s, m.origin_returned_move_id,
                   ml.quantity_product_uom, m.date, ld.usage
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
             WHERE m.state = 'done' AND m.date <= %%s
               AND ml.location_id IN %%s
               AND ml.product_id IN %%s
               AND ml.quantity_product_uom > 0
               %s
               AND (m.origin_returned_move_id IS NOT NULL OR ld.usage = 'supplier')
          ORDER BY m.date ASC, m.id ASC
        """ % (out_wh, out_outside), params)
        for product_id, wh, origin_id, qty, date, dest_usage in self.cr.fetchall():
            qty = float(qty)
            if origin_id:
                entry = entries.get((origin_id, wh))
                if entry is not None:
                    take = min(entry['qty'], qty)
                    entry['qty'] -= take
                    qty -= take
                elif dest_usage != 'supplier':
                    continue  # e.g. re-delivery of a customer return: normal issue
            if qty > 0 and dest_usage == 'supplier':
                for entry in lines.get((product_id, wh), []):
                    if entry['date'] > date or entry['qty'] <= 0:
                        continue
                    take = min(entry['qty'], qty)
                    entry['qty'] -= take
                    qty -= take
                    if qty <= 0:
                        break
        return lines

    def _sql_receipt_dates(self):
        """{(product_id, key): (first_receipt, last_receipt)} over all history up to date_to
        (customer returns and linked returns are not receipts).  Same perimeter rule as
        ``_sql_receipts``: key = 0 in scope mode, warehouse_id in branch mode."""
        res = {}
        if not self.location_ids or not self.product_ids:
            return res
        scope = self.o.aging_scope != 'branch'
        loc = tuple(self.location_ids)
        if scope:
            wh_col, group_by = '0', 'ml.product_id'
            outside = 'AND ml.location_id NOT IN %s'
            params = (self.date_to, loc, tuple(self.product_ids), loc)
        else:
            wh_col = 'COALESCE(ld.warehouse_id, 0)'
            group_by = 'ml.product_id, ' + wh_col
            outside = "AND (ls.usage <> 'internal' OR COALESCE(ls.warehouse_id, 0) <> COALESCE(ld.warehouse_id, 0))"
            params = (self.date_to, loc, tuple(self.product_ids))
        self.cr.execute("""
            SELECT ml.product_id, %s, MIN(m.date), MAX(m.date)
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
              JOIN stock_location ls ON ls.id = ml.location_id
             WHERE m.state = 'done' AND m.date <= %%s
               AND ml.location_dest_id IN %%s
               AND ml.product_id IN %%s
               AND ml.quantity_product_uom > 0
               AND m.origin_returned_move_id IS NULL
               AND ls.usage <> 'customer'
               %s
          GROUP BY %s
        """ % (wh_col, outside, group_by), params)
        for product_id, wh, first, last in self.cr.fetchall():
            res[(product_id, wh)] = (first, last)
        return res

    def _has_pos_refund_link(self):
        """True when Point of Sale is installed (stock_picking.pos_order_id and
        pos_order_line.refunded_orderline_id both exist)."""
        if not hasattr(self, '_pos_link'):
            self.cr.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                 WHERE (table_name = 'stock_picking' AND column_name = 'pos_order_id')
                    OR (table_name = 'pos_order_line' AND column_name = 'refunded_orderline_id')
            """)
            self._pos_link = self.cr.fetchone()[0] >= 2
        return self._pos_link

    def _pos_join_sql(self):
        """LEFT JOIN giving ``pr.date_order`` = date of the refunded POS order (or NULL)."""
        if not self._has_pos_refund_link():
            return '', 'NULL'
        return """
              LEFT JOIN stock_picking sp ON sp.id = m.picking_id
              LEFT JOIN LATERAL (
                    SELECT MIN(oo.date_order) AS date_order
                      FROM pos_order_line rl
                      JOIN pos_order_line ol ON ol.id = rl.refunded_orderline_id
                      JOIN pos_order oo ON oo.id = ol.order_id
                     WHERE rl.order_id = sp.pos_order_id AND rl.product_id = ml.product_id
              ) pr ON TRUE""", 'pr.date_order'

    def _sql_sales(self, window_from, with_last_sale=True):
        """Net customer sales in [window_from, date_to] per (product, wh), plus – optionally – the
        last sale date over all history.  Returns are netted against the ORIGINAL sale date
        (return linked to its delivery, or POS refund linked to the refunded order)."""
        sales = defaultdict(float)
        cogs = defaultdict(float)
        cogs_nolayer_qty = defaultdict(float)
        last_sale = {}
        if not self.location_ids or not self.product_ids:
            return sales, cogs, cogs_nolayer_qty, last_sale
        loc = tuple(self.location_ids)
        prods = tuple(self.product_ids)
        # deliveries to customers (unit cost of the move from its valuation layers)
        self.cr.execute("""
            SELECT ml.product_id, COALESCE(ls.warehouse_id, 0),
                   SUM(CASE WHEN m.date > %s THEN ml.quantity_product_uom ELSE 0 END),
                   SUM(CASE WHEN m.date > %s AND lv.unit_cost IS NOT NULL THEN ml.quantity_product_uom * lv.unit_cost ELSE 0 END),
                   SUM(CASE WHEN m.date > %s AND lv.unit_cost IS NULL THEN ml.quantity_product_uom ELSE 0 END),
                   MAX(m.date)
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
              LEFT JOIN LATERAL (
                    SELECT CASE WHEN SUM(svl.quantity) <> 0 THEN SUM(svl.value) / SUM(svl.quantity) END AS unit_cost
                      FROM stock_valuation_layer svl
                     WHERE svl.stock_move_id = m.id AND svl.company_id = %s
              ) lv ON TRUE
             WHERE m.state = 'done' AND m.date <= %s
               AND ml.location_id IN %s AND ld.usage = 'customer'
               AND ml.product_id IN %s
          GROUP BY ml.product_id, COALESCE(ls.warehouse_id, 0)
        """, (window_from, window_from, window_from, self.company.id, self.date_to, loc, prods))
        for product_id, wh, qty, cost, qty_nolayer, last in self.cr.fetchall():
            sales[(product_id, wh)] += float(qty or 0.0)
            cogs[(product_id, wh)] += float(cost or 0.0)
            cogs_nolayer_qty[(product_id, wh)] += float(qty_nolayer or 0.0)
            if with_last_sale:
                last_sale[(product_id, wh)] = last
        # customer returns, netted at the original sale date
        pos_join, pos_date = self._pos_join_sql()
        self.cr.execute("""
            SELECT ml.product_id, COALESCE(ld.warehouse_id, 0), SUM(ml.quantity_product_uom),
                   SUM(CASE WHEN lv.unit_cost IS NOT NULL THEN ml.quantity_product_uom * lv.unit_cost ELSE 0 END),
                   SUM(CASE WHEN lv.unit_cost IS NULL THEN ml.quantity_product_uom ELSE 0 END)
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              LEFT JOIN stock_move o ON o.id = m.origin_returned_move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
              LEFT JOIN LATERAL (
                    SELECT CASE WHEN SUM(svl.quantity) <> 0 THEN SUM(svl.value) / SUM(svl.quantity) END AS unit_cost
                      FROM stock_valuation_layer svl
                     WHERE svl.stock_move_id = m.id AND svl.company_id = %%s
              ) lv ON TRUE
              %s
             WHERE m.state = 'done' AND m.date <= %%s
               AND COALESCE(o.date, %s, m.date) > %%s AND COALESCE(o.date, %s, m.date) <= %%s
               AND ml.location_dest_id IN %%s AND ls.usage = 'customer'
               AND ml.product_id IN %%s
          GROUP BY ml.product_id, COALESCE(ld.warehouse_id, 0)
        """ % (pos_join, pos_date, pos_date),
            (self.company.id, self.date_to, window_from, self.date_to, loc, prods))
        for product_id, wh, qty, cost, qty_nolayer in self.cr.fetchall():
            sales[(product_id, wh)] -= float(qty or 0.0)
            cogs[(product_id, wh)] -= float(cost or 0.0)
            cogs_nolayer_qty[(product_id, wh)] -= float(qty_nolayer or 0.0)
        return sales, cogs, cogs_nolayer_qty, last_sale

    def _sql_incoming(self):
        """Confirmed (not yet received) purchase / incoming quantities per product (now mode only)."""
        res = defaultdict(float)
        if not self.is_now or not self.location_ids or not self.product_ids:
            return res
        self.cr.execute("""
            SELECT m.product_id, SUM(m.product_qty)
              FROM stock_move m
              JOIN stock_location ls ON ls.id = m.location_id
             WHERE m.state IN ('waiting', 'confirmed', 'assigned', 'partially_available')
               AND m.location_dest_id IN %s AND ls.usage <> 'internal'
               AND m.product_id IN %s
          GROUP BY m.product_id
        """, (tuple(self.location_ids), tuple(self.product_ids)))
        for product_id, qty in self.cr.fetchall():
            res[product_id] += float(qty or 0.0)
        return res

    # ------------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------------
    def _unit_costs(self, products, at_date=None):
        """{product_id: unit cost} according to the cost basis, optionally as of ``at_date``."""
        costs = {}
        if not products:
            return costs
        if self.o.cost_basis == 'svl':
            historical = at_date is not None or not self.is_now
            ctx = {'to_date': at_date or self.date_to} if historical else {}
            prods = products.with_company(self.company).with_context(**ctx)
            for p in prods:
                qty_svl = p.quantity_svl
                if qty_svl and qty_svl > 0 and p.value_svl:
                    costs[p.id] = p.value_svl / qty_svl
                else:
                    costs[p.id] = p.with_company(self.company).standard_price or 0.0
        else:
            for p in products.with_company(self.company):
                costs[p.id] = p.standard_price or 0.0
        return costs

    # ------------------------------------------------------------------
    # Sale price (net of taxes included in the price)
    # ------------------------------------------------------------------
    def _net_price(self, product):
        """Sale price excluding VAT: if the product's sale taxes are configured as included in the
        price, the tax is stripped so that expected cash figures are net of VAT."""
        price = float(product.lst_price or 0.0)
        if price <= 0:
            return 0.0, price
        taxes = product.taxes_id.filtered(lambda t: t.company_id == self.company)
        if not taxes:
            return price, price
        key = (tuple(taxes.ids), price)
        cache = self.__dict__.setdefault('_price_cache', {})
        if key not in cache:
            try:
                res = taxes.compute_all(price, currency=self.currency, quantity=1.0, product=product)
                cache[key] = float(res.get('total_excluded', price))
            except Exception:  # never let a tax configuration issue break the report
                cache[key] = price
        return cache[key], price

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def _classify(self, qty, sales_qty, last_sale, first_receipt, cover_days):
        o = self.o
        if qty <= 0:
            return 'out'
        days_since_sale = self._days(last_sale) if last_sale else None
        if sales_qty > 0:
            if cover_days is not None and cover_days > o.slow_cover_days:
                return 'slow'
            return 'active'
        # no sales in the window
        if days_since_sale is not None and days_since_sale < o.stagnant_days:
            # sold recently (window shorter than stagnation threshold) – treat as active-but-quiet
            return 'active'
        first_days = self._days(first_receipt) if first_receipt else None
        if o.new_days > 0 and first_days is not None and first_days <= o.new_days:
            return 'new'
        return 'stagnant'

    def _recommend(self, row):
        """Return (action_key, action_text) for a product-level row."""
        o = self.o
        st = row['status']
        if st == 'out':
            return 'reorder_urgent', 'إعادة طلب عاجل — الصنف نافد وله طلب مستمر'
        if st == 'new':
            return 'watch', 'صنف جديد — متابعة أدائه قبل أي قرار'
        if st == 'active':
            if row['cover_days'] is not None and row['cover_days'] <= o.reorder_cover_days:
                if row['incoming_qty'] > 0:
                    return 'keep', 'تغطية منخفضة — توجد كمية قادمة (%s)' % fmt_qty(row['incoming_qty'])
                return 'reorder', 'إعادة طلب — التغطية أقل من %d يوم' % o.reorder_cover_days
            return 'keep', 'مستوى مناسب — استمرار البيع'
        if st == 'slow':
            return 'stop_buy', 'إيقاف الشراء وتصريف الفائض بعرض محدود'
        # stagnant
        d = row['days_since_sale']
        age = row['max_age'] if row['max_age'] is not None else 0
        ref = d if d is not None else age
        if d is None and age < o.stagnant_days:
            # never sold but received less than the stagnation window ago: too early for a discount
            return 'watch', 'استُلم منذ %s ولم يُبع بعد — متابعة قبل أي خصم' % ar_days(age)
        if ref >= 365:
            return 'liquidate', 'تصفية فورية — بلا بيع منذ أكثر من سنة'
        if ref >= 180:
            return 'discount_high', 'خصم قوي أو عرض حزمة — بلا بيع منذ أكثر من 6 أشهر'
        return 'discount', 'عرض ترويجي / خصم — بلا بيع منذ %s يوم' % fmt_int(ref)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self):
        self._load_scope()
        on_hand = self._sql_on_hand()
        sales, cogs, cogs_nolayer, last_sale = self._sql_sales(self.sales_from)
        if self.cov_from != self.sales_from:
            cov_sales, _c, _n, _l = self._sql_sales(self.cov_from, with_last_sale=False)
        else:
            cov_sales = sales
        receipt_dates = self._sql_receipt_dates()
        incoming = self._sql_incoming()
        opening = self._sql_on_hand(at_date=self.sales_from) if self.o.date_from else None

        # products that matter: have stock somewhere, sold in the window, or had opening stock.
        # Positive and negative branch balances are kept apart: only positive quantities
        # physically exist and are aged / valued; a negative balance (sales recorded without
        # enough stock) never enters the aging, the quantities or the valuation.
        prod_pos = defaultdict(float)
        prod_neg = defaultdict(float)
        prod_sales = defaultdict(float)
        prod_opening = defaultdict(float)
        for (pid, wh), qty in on_hand.items():
            if qty > 0:
                prod_pos[pid] += qty
            elif qty < 0:
                prod_neg[pid] -= qty
        for (pid, wh), qty in sales.items():
            prod_sales[pid] += qty
        for (pid, wh), qty in (opening or {}).items():
            if qty > 0:
                prod_opening[pid] += qty
        relevant_ids = [p.id for p in self.products
                        if prod_pos.get(p.id, 0.0) > 0 or prod_neg.get(p.id, 0.0) > 0
                        or prod_sales.get(p.id, 0.0) > 0 or prod_opening.get(p.id, 0.0) > 0]
        relevant_set = set(relevant_ids)
        products = self.products.filtered(lambda p: p.id in relevant_set)
        stocked_ids = [pid for pid in relevant_ids if prod_pos.get(pid, 0.0) > 0]
        receipts = self._sql_receipts(stocked_ids)
        unit_costs = self._unit_costs(products)
        opening_costs = self._unit_costs(products, at_date=self.sales_from) if opening is not None else {}

        wh_ids = [wh.id for wh in self.warehouses]
        if any(wh == 0 and qty for (pid, wh), qty in on_hand.items()):
            wh_ids.append(0)
        self.wh_ids = wh_ids

        rows = []
        for p in products.with_company(self.company):
            rounding = p.uom_id.rounding or 0.01
            row = self._build_product_row(p, rounding, on_hand, sales, cov_sales, cogs, cogs_nolayer, last_sale,
                                          receipt_dates, receipts, unit_costs, incoming, opening, opening_costs)
            if row:
                rows.append(row)

        self._compute_transfers(rows)
        return self._assemble(rows)

    # ------------------------------------------------------------------
    def _build_product_row(self, p, rounding, on_hand, sales, cov_sales, cogs, cogs_nolayer, last_sale,
                           receipt_dates, receipts, unit_costs, incoming, opening, opening_costs):
        o = self.o
        # ---- on hand per branch: positive balances are the stock that exists (aged and valued);
        #      negative balances are sales recorded while the branch had no stock -> never aged,
        #      never valued.  net_qty (= positive - negative) is Odoo's "quantity on hand".
        wh_qty = {}
        wh_neg = {}
        total_qty = 0.0
        neg_qty = 0.0
        for wh in self.wh_ids:
            q = float_round(on_hand.get((p.id, wh), 0.0), precision_rounding=rounding)
            if q > 0:
                wh_qty[wh] = q
                total_qty += q
            elif q < 0:
                wh_neg[wh] = -q
                neg_qty -= q
        total_qty = float_round(total_qty, precision_rounding=rounding)
        neg_qty = float_round(neg_qty, precision_rounding=rounding)
        net_qty = float_round(total_qty - neg_qty, precision_rounding=rounding)

        sales_qty = 0.0
        wh_sales = {}
        for wh in self.wh_ids:
            s = sales.get((p.id, wh), 0.0)
            wh_sales[wh] = s
            sales_qty += s
        sales_qty = max(0.0, sales_qty)
        cov_qty = max(0.0, sum(cov_sales.get((p.id, wh), 0.0) for wh in self.wh_ids))
        opening_qty = 0.0
        if opening is not None:
            # a negative opening balance is no stock at all
            opening_qty = float_round(sum(max(0.0, opening.get((p.id, wh), 0.0)) for wh in self.wh_ids),
                                      precision_rounding=rounding)
        if total_qty <= 0 and neg_qty <= 0 and sales_qty <= 0 and opening_qty <= 0:
            return None

        # dates (receipts follow the aging perimeter: scope-wide or per branch)
        scope = o.aging_scope != 'branch'
        last_sale_dt = None
        first_receipt_dt = None
        last_receipt_dt = None
        wh_last_sale = {}
        wh_first_receipt = {}
        for wh in self.wh_ids:
            ls = last_sale.get((p.id, wh))
            wh_last_sale[wh] = ls
            if ls and (last_sale_dt is None or ls > last_sale_dt):
                last_sale_dt = ls
            fr = receipt_dates.get((p.id, 0 if scope else wh))
            if fr:
                wh_first_receipt[wh] = fr[0]
                if first_receipt_dt is None or fr[0] < first_receipt_dt:
                    first_receipt_dt = fr[0]
                if last_receipt_dt is None or fr[1] > last_receipt_dt:
                    last_receipt_dt = fr[1]

        avg_daily = sales_qty / float(self.period_days) if sales_qty > 0 else 0.0
        cover_days = (total_qty / avg_daily) if avg_daily > 0 and total_qty > 0 else None
        avg_daily_cov = cov_qty / float(self.cov_days) if cov_qty > 0 else 0.0
        coverage = (total_qty / avg_daily_cov) if avg_daily_cov > 0 and total_qty > 0 else None

        # ---- aging (FIFO from receipts) per branch, aggregated ----
        # The positive on-hand quantity of a branch is attributed to that branch's receipts,
        # newest first.  Because on hand = receipts - issues, an issue made while the balance
        # was negative reduces the quantity attributed to the NEXT receipt: a purchase arriving
        # after a negative balance first covers that balance and only the remainder is aged
        # from the purchase date (bought 100, sold 200, then bought 200 -> 100 aged from the
        # second purchase).  Negative balances themselves never enter the buckets.
        bucket_qty = [0.0] * self.n_buckets
        age_weighted = 0.0
        max_age = None
        unknown_qty = 0.0
        old_qty = 0.0
        year_qty = 0.0
        wh_avg_age = {}
        wh_bucket_qty = {}      # {wh: [qty per bucket]} — the branch's OWN receipt ages

        def add_age(take, age, wb):
            nonlocal age_weighted, max_age, old_qty, year_qty
            idx = self._bucket_index(age)
            bucket_qty[idx] += take
            wb[idx] += take
            age_weighted += take * age
            max_age = age if max_age is None else max(max_age, age)
            if age > self.old_days:
                old_qty += take
            if age > 365:
                year_qty += take

        def walk(perimeter_key, quantity, wb):
            nonlocal unknown_qty
            remaining = quantity
            weighted = 0.0
            for entry in receipts.get((p.id, perimeter_key), []):
                if remaining <= rounding / 2.0:
                    break
                if entry['qty'] <= 0:
                    continue
                take = min(remaining, entry['qty'])
                age = self._days(entry['date'])
                add_age(take, age, wb)
                weighted += take * age
                remaining -= take
            if remaining > rounding / 2.0:
                # quantity older than any receipt we know of (e.g. migrated stock)
                oldest = receipts.get((p.id, perimeter_key))
                if oldest:
                    age = self._days(oldest[-1]['date'])
                else:
                    age = self._days(p.create_date) if p.create_date else self.buckets[-1] + 1
                    age = max(age, 0)
                add_age(remaining, age, wb)
                weighted += remaining * age
                unknown_qty += remaining
            return weighted

        if scope:
            # ONE perimeter: the whole selection.  Internal transfers inside it are invisible,
            # so the ages come from the dates stock entered the company / selection.
            if total_qty > 0:
                walk(0, total_qty, [0.0] * self.n_buckets)
            avg_age = (age_weighted / total_qty) if total_qty > 0 else None
            for wh, q in wh_qty.items():
                if q <= 0:
                    continue
                # branch split of the scope-level ages, pro-rata to the branch quantity
                wh_bucket_qty[wh] = [b * (q / total_qty) for b in bucket_qty] if total_qty else [0.0] * self.n_buckets
                wh_avg_age[wh] = avg_age or 0.0
        else:
            for wh, q in wh_qty.items():
                if q <= 0:
                    continue
                wb = wh_bucket_qty.setdefault(wh, [0.0] * self.n_buckets)
                weighted = walk(wh, q, wb)
                wh_avg_age[wh] = weighted / q if q else 0.0
            avg_age = (age_weighted / total_qty) if total_qty > 0 else None

        unit_cost = float(unit_costs.get(p.id, 0.0) or 0.0)
        value = total_qty * unit_cost if total_qty > 0 else 0.0
        price, price_incl = self._net_price(p)
        sale_value = total_qty * price if total_qty > 0 else 0.0
        margin_pct = ((price - unit_cost) / price * 100.0) if price > 0 else 0.0
        max_discount = max(0.0, min(100.0, margin_pct))

        status = self._classify(total_qty, sales_qty, last_sale_dt, first_receipt_dt, cover_days)
        days_since_sale = self._days(last_sale_dt) if last_sale_dt else None

        # excess quantity for slow movers = stock beyond the slow-cover threshold
        excess_qty = 0.0
        if status == 'slow' and avg_daily > 0:
            excess_qty = max(0.0, total_qty - avg_daily * o.slow_cover_days)
            excess_qty = float_round(excess_qty, precision_rounding=rounding)
        excess_value = excess_qty * unit_cost

        # ---- turnover ----
        opening_cost = float(opening_costs.get(p.id, unit_cost) or unit_cost) if opening is not None else unit_cost
        opening_value = opening_qty * opening_cost if opening_qty > 0 else 0.0
        wh_cogs = {}
        for wh in self.wh_ids:
            if o.cogs_basis == 'svl':
                c = cogs.get((p.id, wh), 0.0) + cogs_nolayer.get((p.id, wh), 0.0) * unit_cost
            else:
                c = wh_sales.get(wh, 0.0) * unit_cost
            wh_cogs[wh] = max(0.0, c)
        cogs_value = sum(wh_cogs.values())
        avg_inventory = ((opening_value + value) / 2.0) if opening is not None else value
        turnover = (cogs_value / avg_inventory) if avg_inventory > 0 else None
        turnover_annual = (turnover * 365.0 / self.period_days) if turnover is not None else None
        dsi = (self.period_days / turnover) if turnover else None

        # per-branch status (for rebalancing analysis)
        wh_status = {}
        wh_cover = {}
        for wh in self.wh_ids:
            q = wh_qty.get(wh, 0.0)
            s = max(0.0, wh_sales.get(wh, 0.0))
            ad = s / float(self.period_days) if s > 0 else 0.0
            cov = (q / ad) if ad > 0 and q > 0 else None
            wh_cover[wh] = cov
            if q > 0 or s > 0:
                wh_status[wh] = self._classify(q, s, wh_last_sale.get(wh), wh_first_receipt.get(wh), cov)

        wh_text = ' · '.join('%s: %s' % (self.wh_names.get(wh, ''), fmt_qty(q))
                             for wh, q in wh_qty.items() if q) if len(self.wh_ids) > 1 else ''
        variant = ', '.join(p.product_template_attribute_value_ids.mapped('name'))
        name = p.name + (' (%s)' % variant if variant else '')
        if not p.active:
            name = '%s (مؤرشف)' % name
        row = {
            'id': p.id,
            'name': name,
            'name_ltr': bool(re.match(r'^[^\w]*[A-Za-z]', p.name or '')),
            'display_name': p.display_name if p.active else '%s (مؤرشف)' % p.display_name,
            'code': p.default_code or '',
            'wh_text': wh_text,
            'category': p.categ_id.complete_name or p.categ_id.name or '',
            'categ_id': p.categ_id.id,
            'uom': p.uom_id.name or '',
            'archived': not p.active,
            'qty': total_qty,           # positive stock (exists physically): aged and valued
            'neg_qty': neg_qty,         # sum of negative branch balances (never aged nor valued)
            'net_qty': net_qty,         # qty - neg_qty = Odoo's quantity on hand
            'wh_qty': wh_qty,
            'wh_neg': wh_neg,
            'wh_bucket_qty': wh_bucket_qty,
            'wh_sales': wh_sales,
            'wh_cogs': wh_cogs,
            'wh_status': wh_status,
            'wh_cover': wh_cover,
            'wh_avg_age': wh_avg_age,
            'wh_last_sale': wh_last_sale,
            'unit_cost': unit_cost,
            'value': value,
            'price': price,
            'price_incl': price_incl,
            'sale_value': sale_value,
            'margin_pct': margin_pct,
            'max_discount': max_discount,
            'sales_qty': sales_qty,
            'avg_daily': avg_daily,
            'cover_days': cover_days,
            'cov_sales_qty': cov_qty,
            'avg_daily_cov': avg_daily_cov,
            'coverage': coverage,
            'last_sale': last_sale_dt,
            'last_sale_str': self._fmt_date(last_sale_dt) if last_sale_dt else 'لم يُبع',
            'days_since_sale': days_since_sale,
            'first_receipt': first_receipt_dt,
            'first_receipt_str': self._fmt_date(first_receipt_dt) if first_receipt_dt else '-',
            'last_receipt': last_receipt_dt,
            'last_receipt_str': self._fmt_date(last_receipt_dt) if last_receipt_dt else '-',
            'incoming_qty': float(incoming.get(p.id, 0.0)),
            'bucket_qty': bucket_qty,
            'bucket_value': [q * unit_cost for q in bucket_qty],
            'old_qty': old_qty,
            'old_value': old_qty * unit_cost,
            'year_qty': year_qty,
            'year_value': year_qty * unit_cost,
            'avg_age': avg_age,
            'max_age': max_age,
            'unknown_qty': unknown_qty,
            'status': status,
            'status_label': STATUS_LABELS[status],
            'excess_qty': excess_qty,
            'excess_value': excess_value,
            'opening_qty': opening_qty,
            'opening_cost': opening_cost,
            'opening_value': opening_value,
            'cogs': cogs_value,
            'avg_inventory': avg_inventory,
            'turnover': turnover,
            'turnover_annual': turnover_annual,
            'dsi': dsi,
            'transfers': [],
        }
        action, action_text = self._recommend(row)
        row['action'] = action
        row['action_label'] = ACTION_LABELS[action]
        row['action_text'] = action_text

        # liquidation economics (stagnant & slow excess only; items under watch are not liquidated)
        applied = min(self.discount, max_discount / 100.0)
        row['applied_discount'] = applied * 100.0
        if status == 'stagnant' and action != 'watch':
            row['liq_qty'] = total_qty
        elif status == 'slow':
            row['liq_qty'] = excess_qty
        else:
            row['liq_qty'] = 0.0
        row['liq_cost'] = row['liq_qty'] * unit_cost
        row['liq_sale_value'] = row['liq_qty'] * price
        row['expected_cash'] = row['liq_qty'] * price * (1.0 - applied)
        return row

    # ------------------------------------------------------------------
    def _compute_transfers(self, rows):
        """Branch rebalancing: stock idle in one branch while another branch sells it."""
        o = self.o
        if len(self.wh_ids) < 2:
            return
        target_cover = max(30, o.slow_cover_days // 2)
        for row in rows:
            if row['qty'] <= 0:
                continue
            for wh_from, q_from in row['wh_qty'].items():
                if q_from <= 0:
                    continue
                st_from = row['wh_status'].get(wh_from)
                if st_from not in ('stagnant', 'slow'):
                    continue
                best = None
                for wh_to in self.wh_ids:
                    if wh_to == wh_from:
                        continue
                    s_to = max(0.0, row['wh_sales'].get(wh_to, 0.0))
                    if s_to <= 0:
                        continue
                    ad_to = s_to / float(self.period_days)
                    q_to = row['wh_qty'].get(wh_to, 0.0)
                    cov_to = (q_to / ad_to) if ad_to > 0 else None
                    if cov_to is not None and cov_to >= o.slow_cover_days:
                        continue  # the other branch already has plenty
                    need = ad_to * target_cover - q_to
                    if need <= 0:
                        continue
                    if best is None or ad_to > best[1]:
                        best = (wh_to, ad_to, need, cov_to)
                if not best:
                    continue
                wh_to, ad_to, need, cov_to = best
                qty = min(q_from, need)
                qty = math.floor(qty) if qty >= 1 else 0
                if qty <= 0:
                    continue
                row['transfers'].append({
                    'from_id': wh_from,
                    'from_name': self.wh_names.get(wh_from, ''),
                    'from_qty': q_from,
                    'from_days_no_sale': self._days(row['wh_last_sale'].get(wh_from)) if row['wh_last_sale'].get(wh_from) else None,
                    'to_id': wh_to,
                    'to_name': self.wh_names.get(wh_to, ''),
                    'to_qty': row['wh_qty'].get(wh_to, 0.0),
                    'to_avg_daily': ad_to,
                    'to_cover': cov_to,
                    'qty': float(qty),
                    'value': float(qty) * row['unit_cost'],
                })

    # ------------------------------------------------------------------
    def _category_summary(self, name, items, total_value):
        """Aggregate a list of product rows (one category) into one summary dict."""
        n = self.n_buckets

        def pct(part, whole):
            return (part / whole * 100.0) if whole else 0.0

        stocked = [r for r in items if r['qty'] > 0]
        val = sum(r['value'] for r in stocked)
        qty = sum(r['qty'] for r in stocked)
        bucket_qty = [sum(r['bucket_qty'][i] for r in stocked) for i in range(n)]
        bucket_value = [sum(r['bucket_value'][i] for r in stocked) for i in range(n)]
        old_value = sum(r['old_value'] for r in stocked)
        year_value = sum(r['year_value'] for r in stocked)
        wavg = sum((r['avg_age'] or 0.0) * r['qty'] for r in stocked)
        vavg = sum((r['avg_age'] or 0.0) * r['value'] for r in stocked)
        stag = [r for r in stocked if r['status'] == 'stagnant']
        slow = [r for r in stocked if r['status'] == 'slow']
        act = [r for r in stocked if r['status'] == 'active']
        new = [r for r in stocked if r['status'] == 'new']
        stag_val = sum(r['value'] for r in stag)
        cogs = sum(r['cogs'] for r in items)
        opening_qty = sum(r['opening_qty'] for r in items)
        opening_value = sum(r['opening_value'] for r in items)
        avg_inventory = sum(r['avg_inventory'] for r in items)
        turnover = (cogs / avg_inventory) if avg_inventory > 0 else None
        turnover_annual = (turnover * 365.0 / self.period_days) if turnover is not None else None
        dsi = (self.period_days / turnover) if turnover else None
        avg_daily_cov = sum(r['avg_daily_cov'] for r in items)
        coverage = (qty / avg_daily_cov) if avg_daily_cov > 0 and qty > 0 else None
        sales_qty = sum(r['sales_qty'] for r in items)
        return {
            'name': name,
            'name_ltr': bool(re.match(r'^[^\w]*[A-Za-z]', name or '')),
            'categ_id': items[0]['categ_id'] if items else False,
            'count': len(stocked),
            'count_all': len(items),
            'qty': qty,
            'value': val,
            'pct': pct(val, total_value),
            'sale_value': sum(r['sale_value'] for r in stocked),
            'bucket_qty': bucket_qty,
            'bucket_value': bucket_value,
            'bucket_pct': [pct(v, val) for v in bucket_value],
            'last_qty': bucket_qty[-1],
            'last_value': bucket_value[-1],
            'last_pct': pct(bucket_value[-1], val),
            'old_value': old_value,
            'old_pct': pct(old_value, val),
            'year_value': year_value,
            'year_pct': pct(year_value, val),
            'avg_age': (wavg / qty) if qty else 0.0,
            'avg_age_value': (vavg / val) if val else 0.0,
            'max_age': max([r['max_age'] or 0 for r in stocked] + [0]),
            'active_value': sum(r['value'] for r in act),
            'active_count': len(act),
            'slow_value': sum(r['value'] for r in slow),
            'slow_count': len(slow),
            'stagnant_value': stag_val,
            'stagnant_pct': pct(stag_val, val),
            'stagnant_count': len(stag),
            'new_value': sum(r['value'] for r in new),
            'new_count': len(new),
            'sales_qty': sales_qty,
            'cov_sales_qty': sum(r['cov_sales_qty'] for r in items),
            'avg_daily': sales_qty / float(self.period_days) if sales_qty > 0 else 0.0,
            'avg_daily_cov': avg_daily_cov,
            'coverage': coverage,
            'opening_qty': opening_qty,
            'opening_value': opening_value,
            'cogs': cogs,
            'avg_inventory': avg_inventory,
            'turnover': turnover,
            'turnover_annual': turnover_annual,
            'dsi': dsi,
            'rows': items,
        }

    # ------------------------------------------------------------------
    def _assemble(self, rows):
        o = self.o
        cur = self.currency_symbol
        n = self.n_buckets
        stocked = [r for r in rows if r['qty'] > 0]
        total_value = sum(r['value'] for r in stocked)
        total_qty = sum(r['qty'] for r in stocked)
        total_sale_value = sum(r['sale_value'] for r in stocked)

        def pct(part, whole):
            return (part / whole * 100.0) if whole else 0.0

        # ---- status summary (the "new" status exists only when a new-item window is set) ----
        status_summary = []
        for key in STATUS_ORDER:
            grp = [r for r in stocked if r['status'] == key]
            val = sum(r['value'] for r in grp)
            status_summary.append({
                'key': key,
                'label': STATUS_LABELS[key],
                'count': len(grp),
                'qty': sum(r['qty'] for r in grp),
                'value': val,
                'pct': pct(val, total_value),
                'sale_value': sum(r['sale_value'] for r in grp),
            })
        status_by_key = {s['key']: s for s in status_summary}
        if o.new_days <= 0:
            status_summary = [s for s in status_summary if s['key'] != 'new']
        max_status_pct = max([s['pct'] for s in status_summary] + [1.0])
        bar_classes = {'active': '', 'slow': 'amber', 'stagnant': 'red', 'new': 'blue'}
        for s in status_summary:
            s['bar'] = pct(s['pct'], max_status_pct)
            s['bar_class'] = bar_classes[s['key']]

        # ---- aging buckets ----
        buckets = []
        for i, label in enumerate(self.bucket_labels):
            bq = sum(r['bucket_qty'][i] for r in stocked)
            bv = sum(r['bucket_value'][i] for r in stocked)
            buckets.append({'index': i, 'label': label, 'qty': bq, 'value': bv, 'pct': pct(bv, total_value),
                            'pct_qty': pct(bq, total_qty)})
        max_b = max([b['pct'] for b in buckets] + [1.0])
        mid_from = max(1, self.old_from // 2)
        for b in buckets:
            b['bar'] = pct(b['pct'], max_b)
            b['is_old'] = b['index'] >= self.old_from
            b['bar_class'] = 'red' if b['is_old'] else ('gold' if b['index'] >= mid_from else '')
        weighted = sum((r['avg_age'] or 0.0) * r['qty'] for r in stocked)
        avg_age = (weighted / total_qty) if total_qty else 0.0
        value_weighted = sum((r['avg_age'] or 0.0) * r['value'] for r in stocked)
        avg_age_value = (value_weighted / total_value) if total_value else 0.0
        old_value = sum(r['old_value'] for r in stocked)
        old_qty = sum(r['old_qty'] for r in stocked)
        over_year_value = sum(r['year_value'] for r in stocked)
        over_year_qty = sum(r['year_qty'] for r in stocked)
        max_age = max([r['max_age'] or 0 for r in stocked] + [0])
        # the last bucket ("more than X days") is THE old-stock figure of the aging report
        last_qty = buckets[-1]['qty']
        last_value = buckets[-1]['value']

        # ---- aging by category / warehouse matrices ----
        def matrix(group_key, name_of):
            groups = defaultdict(lambda: {'values': [0.0] * n, 'qty': [0.0] * n, 'total': 0.0, 'total_qty': 0.0,
                                          'old': 0.0})
            for r in stocked:
                for keys, share in group_key(r):
                    g = groups[keys]
                    for i in range(n):
                        g['values'][i] += r['bucket_value'][i] * share
                        g['qty'][i] += r['bucket_qty'][i] * share
                    g['total'] += r['value'] * share
                    g['total_qty'] += r['qty'] * share
                    g['old'] += r['old_value'] * share
            out = []
            for k, g in groups.items():
                out.append({'key': k, 'name': name_of(k), 'values': g['values'], 'qty': g['qty'],
                            'total': g['total'], 'total_qty': g['total_qty'],
                            'pct_old': pct(g['old'], g['total']),
                            'pct_last': pct(g['values'][-1], g['total'])})
            out.sort(key=lambda x: -x['total'])
            totals = [sum(x['values'][i] for x in out) for i in range(n)]
            totals_qty = [sum(x['qty'][i] for x in out) for i in range(n)]
            total = sum(x['total'] for x in out)
            return {'columns': self.bucket_labels, 'rows': out, 'totals': totals, 'totals_qty': totals_qty,
                    'total': total, 'total_qty': sum(x['total_qty'] for x in out),
                    'pct_last': pct(totals[-1], total) if totals else 0.0}

        aging_by_category = matrix(lambda r: [(r['category'], 1.0)], lambda k: k)

        # per warehouse: the REAL age distribution of each branch, from the branch's own
        # receipts in the FIFO walk (wh_bucket_qty) — never a pro-rata split of the product total
        wh_rows = []
        for wh in self.wh_ids:
            qtys = [0.0] * n
            values = [0.0] * n
            for r in stocked:
                wb = r['wh_bucket_qty'].get(wh)
                if not wb:
                    continue
                for i in range(n):
                    if wb[i]:
                        qtys[i] += wb[i]
                        values[i] += wb[i] * r['unit_cost']
            total_v = sum(values)
            total_q = sum(qtys)
            if total_q <= 0 and total_v <= 0:
                continue
            wh_rows.append({'key': wh, 'name': self.wh_names.get(wh, ''), 'values': values, 'qty': qtys,
                            'total': total_v, 'total_qty': total_q,
                            'pct_old': pct(sum(values[self.old_from:]), total_v),
                            'pct_last': pct(values[-1], total_v)})
        wh_rows.sort(key=lambda x: -x['total'])
        wh_totals = [sum(x['values'][i] for x in wh_rows) for i in range(n)]
        wh_totals_qty = [sum(x['qty'][i] for x in wh_rows) for i in range(n)]
        wh_total = sum(x['total'] for x in wh_rows)
        aging_by_warehouse = {'columns': self.bucket_labels, 'rows': wh_rows, 'totals': wh_totals,
                              'totals_qty': wh_totals_qty, 'total': wh_total,
                              'total_qty': sum(x['total_qty'] for x in wh_rows),
                              'pct_last': pct(wh_totals[-1], wh_total) if wh_totals else 0.0}

        # ---- by warehouse ----
        by_warehouse = []
        for wh in self.wh_ids:
            items = [r for r in stocked if r['wh_qty'].get(wh, 0.0) > 0]
            if not items and wh == 0:
                continue
            val = sum(r['wh_qty'][wh] * r['unit_cost'] for r in items)
            qty = sum(r['wh_qty'][wh] for r in items)
            stag = [r for r in items if r['status'] == 'stagnant']
            slow = [r for r in items if r['status'] == 'slow']
            act = [r for r in items if r['status'] == 'active']
            stag_val = sum(r['wh_qty'][wh] * r['unit_cost'] for r in stag)
            slow_val = sum(r['wh_qty'][wh] * r['unit_cost'] for r in slow)
            act_val = sum(r['wh_qty'][wh] * r['unit_cost'] for r in act)
            # branch-level idle stock (no sales in this branch) regardless of company status
            idle = [r for r in items if r['wh_status'].get(wh) == 'stagnant']
            idle_val = sum(r['wh_qty'][wh] * r['unit_cost'] for r in idle)
            wavg = sum(r['wh_avg_age'].get(wh, 0.0) * r['wh_qty'][wh] for r in items)
            sales_qty = sum(max(0.0, r['wh_sales'].get(wh, 0.0)) for r in rows)
            cogs = sum(r['wh_cogs'].get(wh, 0.0) for r in rows)
            turnover = (cogs * 365.0 / self.period_days / val) if val else 0.0
            by_warehouse.append({
                'turnover': turnover,
                'dsi': (365.0 / turnover) if turnover else None,
                'id': wh,
                'name': self.wh_names.get(wh, ''),
                'count': len(items),
                'qty': qty,
                'value': val,
                'pct': pct(val, total_value),
                'active_value': act_val,
                'slow_value': slow_val,
                'stagnant_value': stag_val,
                'stagnant_pct': pct(stag_val, val),
                'stagnant_count': len(stag),
                'idle_count': len(idle),
                'idle_value': idle_val,
                'avg_age': (wavg / qty) if qty else 0.0,
                'sales_qty': sales_qty,
            })

        # ---- categories (detailed, with product rows) ----
        cat_groups = defaultdict(list)
        for r in rows:
            cat_groups[r['category']].append(r)
        categories = []
        for name, items in cat_groups.items():
            items.sort(key=lambda r: (-r['value'], -r['sales_qty'], r['name']))
            categories.append(self._category_summary(name, items, total_value))
        categories.sort(key=lambda c: (-c['value'], c['name']))
        by_category = [c for c in categories if c['count'] > 0]

        # ---- detail lists ----
        stagnant_rows = sorted([r for r in stocked if r['status'] == 'stagnant'],
                               key=lambda r: (-r['value'], -(r['days_since_sale'] or r['max_age'] or 0)))
        slow_rows = sorted([r for r in stocked if r['status'] == 'slow'], key=lambda r: -r['excess_value'])
        active_rows = sorted([r for r in stocked if r['status'] == 'active'], key=lambda r: -r['sales_qty'])
        new_rows = sorted([r for r in stocked if r['status'] == 'new'], key=lambda r: -r['value'])
        out_rows = sorted([r for r in rows if r['status'] == 'out' and r['sales_qty'] > 0], key=lambda r: -r['sales_qty'])
        transfer_rows = []
        for r in rows:
            for t in r['transfers']:
                transfer_rows.append(dict(t, product=r['name'], name_ltr=r['name_ltr'], category=r['category'],
                                          unit_cost=r['unit_cost']))
        transfer_rows.sort(key=lambda t: -t['value'])

        # ---- liquidation plan (grouped by action) ----
        plan_order = ['liquidate', 'discount_high', 'discount', 'stop_buy']
        plan_rows = []
        for key in plan_order:
            grp = [r for r in stocked if r['action'] == key and r['liq_qty'] > 0]
            if not grp:
                continue
            plan_rows.append({
                'key': key,
                'label': ACTION_LABELS[key],
                'count': len(grp),
                'qty': sum(r['liq_qty'] for r in grp),
                'cost': sum(r['liq_cost'] for r in grp),
                'sale_value': sum(r['liq_sale_value'] for r in grp),
                'expected_cash': sum(r['expected_cash'] for r in grp),
            })
        plan_total = {
            'count': sum(x['count'] for x in plan_rows),
            'qty': sum(x['qty'] for x in plan_rows),
            'cost': sum(x['cost'] for x in plan_rows),
            'sale_value': sum(x['sale_value'] for x in plan_rows),
            'expected_cash': sum(x['expected_cash'] for x in plan_rows),
        }
        for pl in plan_rows:
            pl['recovery_pct'] = pct(pl['expected_cash'], pl['cost'])
        plan_total['recovery_pct'] = pct(plan_total['expected_cash'], plan_total['cost'])
        transfer_value = sum(t['value'] for t in transfer_rows)
        reorder_rows = [r for r in active_rows if r['action'] == 'reorder']

        stagnant_value = status_by_key['stagnant']['value']
        slow_value = status_by_key['slow']['value']
        active_value = status_by_key['active']['value']
        stagnant_cash = sum(r['expected_cash'] for r in stagnant_rows)
        stagnant_no_sale_ever = [r for r in stagnant_rows if r['last_sale'] is None]

        # ---- section totals (precomputed for the templates) ----
        section_totals = {
            'stagnant_qty': sum(r['qty'] for r in stagnant_rows),
            'stagnant_count': len(stagnant_rows),
            'stagnant_items': ar_items(len(stagnant_rows)),
            'slow_items': ar_items(len(slow_rows)),
            'active_items': ar_items(len(active_rows)),
            'new_items': ar_items(len(new_rows)),
            'out_items': ar_items(len(out_rows)),
            'transfer_items': ar_count(len(transfer_rows), 'اقتراح', 'اقتراحان', 'اقتراحات', 'اقتراحاً'),
            'stagnant_cash': stagnant_cash,
            'stagnant_value': stagnant_value,
            'slow_qty': sum(r['qty'] for r in slow_rows),
            'slow_count': len(slow_rows),
            'slow_value': slow_value,
            'slow_excess_qty': sum(r['excess_qty'] for r in slow_rows),
            'slow_excess_value': sum(r['excess_value'] for r in slow_rows),
            'slow_cash': sum(r['expected_cash'] for r in slow_rows),
            'active_qty': sum(r['qty'] for r in active_rows),
            'active_count': len(active_rows),
            'active_value': active_value,
            'active_sales_qty': sum(r['sales_qty'] for r in active_rows),
            'new_qty': sum(r['qty'] for r in new_rows),
            'new_count': len(new_rows),
            'new_value': sum(r['value'] for r in new_rows),
            'transfer_qty': sum(t['qty'] for t in transfer_rows),
            'transfer_count': len(transfer_rows),
            'transfer_value': transfer_value,
            'out_count': len(out_rows),
            'out_sales_qty': sum(r['sales_qty'] for r in out_rows),
        }

        # ---- status groups (rows grouped by category, for the item-status report) ----
        def group_by_category(items):
            groups = defaultdict(list)
            for r in items:
                groups[r['category']].append(r)
            out = []
            for cname, grp in groups.items():
                out.append({'name': cname, 'name_ltr': bool(re.match(r'^[^\w]*[A-Za-z]', cname or '')),
                            'rows': grp, 'count': len(grp), 'qty': sum(r['qty'] for r in grp),
                            'value': sum(r['value'] for r in grp), 'sales_qty': sum(r['sales_qty'] for r in grp),
                            'expected_cash': sum(r['expected_cash'] for r in grp)})
            out.sort(key=lambda g: (-g['value'], g['name']))
            return out

        status_groups = {}
        for key, items in (('stagnant', stagnant_rows), ('slow', slow_rows), ('active', active_rows),
                           ('new', new_rows), ('out', out_rows)):
            status_groups[key] = {
                'key': key,
                'label': STATUS_LABELS[key],
                'rows': items,
                'groups': group_by_category(items),
                'count': len(items),
                'items': ar_items(len(items)),
                'qty': sum(r['qty'] for r in items),
                'value': sum(r['value'] for r in items),
                'sales_qty': sum(r['sales_qty'] for r in items),
                'expected_cash': sum(r['expected_cash'] for r in items),
            }

        # ---- turnover (whole scope) ----
        cogs_total = sum(r['cogs'] for r in rows)
        opening_value_total = sum(r['opening_value'] for r in rows)
        opening_qty_total = sum(r['opening_qty'] for r in rows)
        avg_inventory_total = sum(r['avg_inventory'] for r in rows)
        turnover_total = (cogs_total / avg_inventory_total) if avg_inventory_total > 0 else None
        turnover_annual_total = (turnover_total * 365.0 / self.period_days) if turnover_total is not None else None
        dsi_total = (self.period_days / turnover_total) if turnover_total else None
        avg_daily_cov_total = sum(r['avg_daily_cov'] for r in rows)
        coverage_total = (total_qty / avg_daily_cov_total) if avg_daily_cov_total > 0 and total_qty > 0 else None
        sales_qty_total = sum(r['sales_qty'] for r in rows)
        turnover_rows = sorted([r for r in rows if r['qty'] > 0 or r['sales_qty'] > 0],
                               key=lambda r: (-(r['turnover_annual'] or 0.0), -r['value']))
        # most / least turning products and products without any turnover in the period
        top_n = max(1, int(o.top_n or 10))
        turning = [r for r in turnover_rows if (r['turnover_annual'] or 0.0) > 0]
        turnover_top = turning[:top_n]
        turnover_bottom = sorted([r for r in turning if r['qty'] > 0],
                                 key=lambda r: ((r['turnover_annual'] or 0.0), -r['value']))[:top_n]
        no_turnover_all = sorted([r for r in stocked if not (r['turnover_annual'] or 0.0)],
                                 key=lambda r: (-r['value'], r['name']))
        no_turnover_value = sum(r['value'] for r in no_turnover_all)
        turnover_lists = {
            'top': turnover_top,
            'bottom': turnover_bottom,
            'none': no_turnover_all[:top_n],
            'none_all': no_turnover_all,
            'none_count': len(no_turnover_all),
            'none_items': ar_items(len(no_turnover_all)),
            'none_qty': sum(r['qty'] for r in no_turnover_all),
            'none_value': no_turnover_value,
            'none_pct': pct(no_turnover_value, total_value),
            'top_n': top_n,
        }

        # ---- KPI ----
        kpi = {
            'cogs_window': cogs_total,
            'turnover': turnover_annual_total or 0.0,
            'turnover_period': turnover_total,
            'turnover_annual': turnover_annual_total,
            'dsi': dsi_total,
            'coverage': coverage_total,
            'avg_daily_cov': avg_daily_cov_total,
            'sales_qty': sales_qty_total,
            'opening_value': opening_value_total,
            'opening_qty': opening_qty_total,
            'avg_inventory': avg_inventory_total,
            'total_value': total_value,
            'total_sale_value': total_sale_value,
            'total_qty': total_qty,
            'product_count': len(stocked),
            'product_count_all': len(rows),
            'active_value': active_value,
            'active_pct': pct(active_value, total_value),
            'active_count': status_by_key['active']['count'],
            'slow_value': slow_value,
            'slow_pct': pct(slow_value, total_value),
            'slow_count': status_by_key['slow']['count'],
            'stagnant_value': stagnant_value,
            'stagnant_pct': pct(stagnant_value, total_value),
            'stagnant_count': status_by_key['stagnant']['count'],
            'new_value': status_by_key['new']['value'],
            'new_count': status_by_key['new']['count'],
            'avg_age': avg_age,
            'avg_age_value': avg_age_value,
            'max_age': max_age,
            'old_value': old_value,
            'old_qty': old_qty,
            'old_pct': pct(old_value, total_value),
            'over_year_value': over_year_value,
            'over_year_qty': over_year_qty,
            'over_year_pct': pct(over_year_value, total_value),
            'last_qty': last_qty,
            'last_value': last_value,
            'last_pct': pct(last_value, total_value),
            'expected_cash': plan_total['expected_cash'],
            'stagnant_cash': stagnant_cash,
            'out_count': len(out_rows),
            'reorder_count': len(reorder_rows),
            'transfer_count': len(transfer_rows),
            'transfer_value': transfer_value,
            'health_score': self._health_score(pct(active_value, total_value), pct(stagnant_value, total_value),
                                               pct(slow_value, total_value)),
            'no_turnover_count': len(no_turnover_all),
            'no_turnover_value': no_turnover_value,
            'no_turnover_pct': pct(no_turnover_value, total_value),
        }
        kpi['health_label'] = self._health_label(kpi['health_score'])

        insights = self._insights(kpi, status_by_key, buckets, by_warehouse, by_category, stagnant_rows,
                                  slow_rows, out_rows, transfer_rows, stagnant_no_sale_ever, plan_total)

        meta = {
            'company_name': self.company.name,
            'currency': cur,
            'currency_name': '%s (%s)' % (self.currency.currency_unit_label or self.currency.name, cur)
            if self.currency.name != 'SAR' else 'ريال سعودي (ر.س)',
            'date_to_display': self._fmt_datetime(self.date_to),
            'date_to_date': self._fmt_date(self.date_to),
            'date_from_date': self._fmt_date(self.sales_from),
            'print_date': self._fmt_datetime(self.now),
            'mode': 'now' if self.is_now else 'historical',
            'mode_label': 'الأرصدة الفعلية الحالية' if self.is_now else 'أرصدة معاد بناؤها بتاريخ سابق',
            'warehouses_display': '، '.join(self.wh_names[wh] for wh in self.wh_ids if wh in self.wh_names and (wh != 0)) or 'جميع الفروع',
            'locations_display': '، '.join(o.location_ids.mapped('complete_name')) if o.location_ids else 'جميع المواقع الداخلية',
            'categories_display': '، '.join(o.categ_ids.mapped('complete_name')) if o.categ_ids else 'جميع الفئات',
            'products_display': '%d صنف محدد' % len(o.product_ids) if o.product_ids else '',
            'sales_from': self._fmt_date(self.sales_from),
            'sales_to': self._fmt_date(self.date_to),
            'sales_days': self.period_days,
            'period_days': self.period_days,
            'coverage_days': self.cov_days,
            'coverage_from': self._fmt_date(self.cov_from),
            'stagnant_days': o.stagnant_days,
            'new_days': o.new_days,
            'has_new_status': o.new_days > 0,
            'slow_cover_days': o.slow_cover_days,
            'reorder_cover_days': o.reorder_cover_days,
            'liquidation_discount': o.liquidation_discount,
            'cost_basis_label': COST_BASIS_LABELS.get(o.cost_basis, ''),
            'cogs_basis_label': COGS_BASIS_LABELS.get(o.cogs_basis, ''),
            'aging_scope': o.aging_scope,
            'aging_scope_label': (
                'منذ دخول %s — التحويلات الداخلية بين الفروع/المواقع المحددة لا تُحتسب استلاماً ولا تبدأ عمراً جديداً'
                % ('الشركة' if not (o.warehouse_ids or o.location_ids) else 'النطاق المحدد (الفروع/المواقع المختارة)')
            ) if o.aging_scope != 'branch' else
                'منذ دخول الفرع — التحويل بين الفروع يُحتسب استلاماً ويبدأ عمراً جديداً في الفرع المستقبِل',
            'wh_aging_hint': (
                'توزيع تقريبي بنِسب كميات الفروع — الأعمار محسوبة على مستوى النطاق كاملاً'
                if o.aging_scope != 'branch' else
                'أعمار كل فرع من استلاماته الفعلية'),
            'bucket_labels': self.bucket_labels,
            'buckets': self.buckets,
            'n_buckets': n,
            'last_label': self.bucket_labels[-1],
            'last_days': self.buckets[-1],
            'old_days': self.old_days,
            'old_from': self.old_from,
            'top_n': top_n,
            'max_lines': o.max_lines,
            'warehouses': [{'id': wh, 'name': self.wh_names.get(wh, '')} for wh in self.wh_ids],
            'multi_warehouse': len(self.wh_ids) > 1,
            'show_active': o.show_active,
            'show_out_of_stock': o.show_out_of_stock,
            'show_category_aging': o.show_category_aging,
        }

        return {
            'meta': meta,
            'kpi': kpi,
            'status_summary': status_summary,
            'status_total': {'count': len(stocked), 'qty': total_qty, 'value': total_value,
                             'sale_value': total_sale_value},
            'aging': {'buckets': buckets, 'total_qty': total_qty, 'total_value': total_value,
                      'avg_age': avg_age, 'avg_age_value': avg_age_value},
            'aging_by_category': aging_by_category,
            'aging_by_warehouse': aging_by_warehouse,
            'by_warehouse': by_warehouse,
            'by_category': by_category,
            'categories': categories,
            'turnover_rows': turnover_rows,
            'turnover_lists': turnover_lists,
            'status_groups': status_groups,
            'stagnant': stagnant_rows,
            'slow': slow_rows,
            'active': active_rows,
            'new': new_rows,
            'out': out_rows,
            'transfers': transfer_rows,
            'reorder': reorder_rows,
            'plan': {'rows': plan_rows, 'total': plan_total},
            'totals': section_totals,
            'insights': insights,
            'all_products': sorted([r for r in rows if r['qty'] > 0 or r['sales_qty'] > 0 or r['neg_qty'] > 0],
                                   key=lambda r: (-r['value'], r['name'])),
            'stocked': sorted(stocked, key=lambda r: (-r['value'], r['name'])),
            # top 10 by value in the LAST bucket ("more than X days")
            'oldest': sorted([r for r in stocked if r['bucket_value'][-1] > 0],
                             key=lambda r: (-(r['bucket_value'][-1]), -(r['max_age'] or 0)))[:10],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _health_score(active_pct, stagnant_pct, slow_pct):
        """0-100 inventory health score: 100 minus the value tied up in stagnant stock
        (weight 1.5) and in slow-moving stock (weight 0.75)."""
        score = 100.0 - 1.5 * stagnant_pct - 0.75 * slow_pct
        return max(0.0, min(100.0, score))

    @staticmethod
    def _health_label(score):
        if score >= 75:
            return 'جيد'
        if score >= 50:
            return 'مقبول — يحتاج متابعة'
        if score >= 30:
            return 'ضعيف — يحتاج إجراءات'
        return 'حرج — يحتاج تدخلاً عاجلاً'

    def _insights(self, kpi, status_by_key, buckets, by_warehouse, by_category, stagnant_rows, slow_rows,
                  out_rows, transfer_rows, never_sold, plan_total):
        """Plain-language findings for management."""
        o = self.o
        cur = self.currency_symbol
        out = []
        if kpi['total_value'] <= 0:
            return ['لا يوجد مخزون ضمن نطاق التقرير المحدد.']
        out.append('إجمالي المخزون %s بقيمة %s %s بالتكلفة (وقيمة بيعية %s %s بالأسعار الحالية).' % (
            ar_items(kpi['product_count']), fmt_money(kpi['total_value']), cur, fmt_money(kpi['total_sale_value']), cur))
        out.append('المخزون النشط يمثل %s من القيمة (%s)، والراكد %s (%s بقيمة %s %s)، وبطيء الحركة %s (%s).' % (
            fmt_pct(kpi['active_pct']), ar_items(kpi['active_count']), fmt_pct(kpi['stagnant_pct']),
            ar_items(kpi['stagnant_count']), fmt_money(kpi['stagnant_value']), cur, fmt_pct(kpi['slow_pct']),
            ar_items(kpi['slow_count'])))
        if never_sold:
            out.append('%s من الأصناف الراكدة لم يُسجل لها أي بيع منذ استلامها (قيمتها %s %s).' % (
                ar_items(len(never_sold)), fmt_money(sum(r['value'] for r in never_sold)), cur))
        out.append('متوسط عمر المخزون %s؛ %s من القيمة عمرها أكثر من %s، و%s أكثر من سنة (%s %s).' % (
            ar_days(kpi['avg_age']), fmt_pct(kpi['old_pct']), ar_days(self.old_days), fmt_pct(kpi['over_year_pct']),
            fmt_money(kpi['over_year_value']), cur))
        if kpi['turnover']:
            out.append('معدل دوران المخزون الحالي %s مرة سنوياً (أي أن المخزون يكفي نحو %s بمعدل البيع الحالي).' % (
                '{:.1f}'.format(kpi['turnover']), ar_days(kpi['dsi'])))
        if stagnant_rows:
            top = stagnant_rows[:3]
            out.append('أكبر الأصناف الراكدة قيمةً: %s.' % '، '.join(
                '%s (%s %s)' % (r['name'], fmt_money(r['value']), cur) for r in top))
        if plan_total['expected_cash'] > 0:
            out.append('تنفيذ خطة التصفية المقترحة (بخصم يصل إلى %s%% دون البيع تحت التكلفة) يوفر سيولة تقديرية %s %s '
                       'مقابل مخزون تكلفته %s %s.' % (
                           fmt_qty(o.liquidation_discount), fmt_money(plan_total['expected_cash']), cur,
                           fmt_money(plan_total['cost']), cur))
        if len(by_warehouse) > 1:
            worst = max(by_warehouse, key=lambda x: x['stagnant_pct'])
            if worst['stagnant_value'] > 0:
                out.append('أعلى نسبة ركود في فرع %s: %s من قيمة مخزونه (%s %s).' % (
                    worst['name'], fmt_pct(worst['stagnant_pct']), fmt_money(worst['stagnant_value']), cur))
        if by_category:
            worst_c = max(by_category, key=lambda x: x['stagnant_value'])
            if worst_c['stagnant_value'] > 0:
                out.append('الفئة الأكثر ركوداً: %s بقيمة راكدة %s %s (%s من مخزون الفئة).' % (
                    worst_c['name'], fmt_money(worst_c['stagnant_value']), cur, fmt_pct(worst_c['stagnant_pct'])))
        if transfer_rows:
            out.append('يمكن إعادة توزيع %s بين الفروع (بقيمة %s %s) بدلاً من تخفيض الأسعار، لأنها تُباع في فرع آخر.' % (
                ar_items(len(transfer_rows)), fmt_money(kpi['transfer_value']), cur))
        if slow_rows:
            out.append('الأصناف بطيئة الحركة تحمل فائضاً بقيمة %s %s فوق تغطية %s — يُنصح بإيقاف شرائها مؤقتاً.' % (
                fmt_money(sum(r['excess_value'] for r in slow_rows)), cur, ar_days(o.slow_cover_days)))
        if out_rows:
            out.append('%s نافدة لها طلب خلال فترة التحليل — فرص بيع مفقودة تستدعي إعادة الطلب.' % ar_items(len(out_rows)))
        if kpi['reorder_count']:
            out.append('%s من الأصناف النشطة تغطيتها أقل من %s وتحتاج إعادة طلب.' % (
                ar_items(kpi['reorder_count']), ar_days(o.reorder_cover_days)))
        return out
