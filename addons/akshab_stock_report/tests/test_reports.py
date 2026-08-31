# -*- coding: utf-8 -*-
"""Automated checks for the Akshab inventory reports.

Everything runs inside the test transaction (rolled back afterwards): the tests create their own
products / moves and never touch existing business data.
"""
import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAkshabStockReports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.now = fields.Datetime.now().replace(microsecond=0)
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.supplier_loc = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_loc = cls.env.ref('stock.stock_location_customers')
        cls.categ = cls.env['product.category'].create({
            'name': 'AKS Test Category', 'property_cost_method': 'average', 'property_valuation': 'manual_periodic'})
        cls.product = cls.env['product.product'].create({
            'name': 'AKS Test Product', 'type': 'consu', 'is_storable': True, 'categ_id': cls.categ.id,
            'default_code': 'AKS-T1', 'standard_price': 10.0, 'list_price': 25.0})

    # ------------------------------------------------------------------
    def _backdate(self, move, date):
        self.env.flush_all()
        self.env.cr.execute("UPDATE stock_move SET date=%s WHERE id=%s", (date, move.id))
        self.env.cr.execute("UPDATE stock_move_line SET date=%s WHERE move_id=%s", (date, move.id))
        self.env.cr.execute("UPDATE stock_valuation_layer SET create_date=%s WHERE stock_move_id=%s", (date, move.id))
        self.env.invalidate_all()

    def _move(self, product, src, dest, qty, days_ago, origin=None):
        vals = {'name': 'test', 'product_id': product.id, 'product_uom_qty': qty, 'product_uom': product.uom_id.id,
                'location_id': src.id, 'location_dest_id': dest.id, 'company_id': self.company.id}
        if origin is not None:
            vals['origin_returned_move_id'] = origin.id
        move = self.env['stock.move'].create(vals)
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()
        self.assertEqual(move.state, 'done')
        self._backdate(move, self.now - timedelta(days=days_ago, hours=1))
        return move

    def _row(self, data, product):
        for r in data['all_products']:
            if r['id'] == product.id:
                return r
        return None

    # ------------------------------------------------------------------
    def test_01_all_wizards_build_render_export(self):
        """The four wizards build their data, render the QWeb report and export Excel without error."""
        for model, report in (
                ('akshab.stock.report.wizard', 'akshab_stock_report.report_akshab_stock_document'),
                ('akshab.stock.aging.wizard', 'akshab_stock_report.report_aging_doc'),
                ('akshab.stock.turnover.wizard', 'akshab_stock_report.report_turnover_doc'),
                ('akshab.stock.status.wizard', 'akshab_stock_report.report_status_doc')):
            wizard = self.env[model].create({'warehouse_ids': [(6, 0, self.warehouse.ids)]})
            data = wizard._build_report_data()
            self.assertIn('kpi', data)
            html = self.env['ir.actions.report']._render_qweb_html(report, wizard.ids)[0]
            self.assertTrue(html)
            action = wizard.action_export_xlsx()
            self.assertEqual(action['type'], 'ir.actions.act_url')
            self.assertTrue(base64.b64decode(wizard.xlsx_file).startswith(b'PK'))  # a valid xlsx (zip) file

    def test_02_quantities_and_value_reconcile_with_odoo(self):
        """On-hand quantity and valuation of the report match Odoo's own figures."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 40, 50)
        self._move(self.product, self.stock_loc, self.customer_loc, 5, 10)
        wizard = self.env['akshab.stock.report.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, self.product.ids)]})
        data = wizard._build_report_data()
        row = self._row(data, self.product)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['qty'], self.product.with_context(warehouse_id=self.warehouse.id).qty_available, places=2)
        self.assertAlmostEqual(row['qty'], 35.0, places=2)
        self.assertAlmostEqual(data['kpi']['total_value'], self.product.value_svl, places=2)
        # totals of every section reconcile with the grand total
        k = data['kpi']
        self.assertAlmostEqual(sum(s['value'] for s in data['status_summary']), k['total_value'], places=2)
        self.assertAlmostEqual(sum(b['value'] for b in data['aging']['buckets']), k['total_value'], places=2)
        self.assertAlmostEqual(sum(c['value'] for c in data['by_category']), k['total_value'], places=2)

    def test_03_purchase_return_reduces_original_receipt(self):
        """May 100 + June 100 − 20 returned against June's receipt → May 100 / June 80 (not May 80)."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 100, 121)
        june = self._move(self.product, self.supplier_loc, self.stock_loc, 100, 90)
        self._move(self.product, self.stock_loc, self.supplier_loc, 20, 80, origin=june)
        wizard = self.env['akshab.stock.report.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, self.product.ids)]})
        data = wizard._build_report_data()
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['qty'], 180.0, places=2)
        labels = data['meta']['bucket_labels']
        buckets = dict(zip(labels, row['bucket_qty']))
        self.assertAlmostEqual(buckets['61 – 90 يوم'], 80.0, places=2)
        self.assertAlmostEqual(buckets['91 – 180 يوم'], 100.0, places=2)

    def test_04_customer_return_keeps_original_age_and_sale_date(self):
        """A return linked to an old delivery is netted at the ORIGINAL sale date and is not a new receipt."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 50, 200)
        delivery = self._move(self.product, self.stock_loc, self.customer_loc, 10, 150)
        self._move(self.product, self.customer_loc, self.stock_loc, 3, 20, origin=delivery)
        self._move(self.product, self.stock_loc, self.customer_loc, 5, 30)
        wizard = self.env['akshab.stock.report.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, self.product.ids)], 'sales_days': 90})
        data = wizard._build_report_data()
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['qty'], 38.0, places=2)
        self.assertAlmostEqual(row['sales_qty'], 5.0, places=2)          # the return hits the 150-day-old sale, outside the window
        self.assertAlmostEqual(row['bucket_qty'][0], 0.0, places=2)      # nothing aged 0-30 days
        self.assertAlmostEqual(sum(row['bucket_qty']), 38.0, places=2)
        self.assertGreaterEqual(row['max_age'], 199)

    def test_05_turnover_equation(self):
        """Turnover components: average inventory, COGS, turnover, inventory days, coverage."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 100, 120)   # opening stock for a 90-day period
        self._move(self.product, self.stock_loc, self.customer_loc, 30, 40)
        wizard = self.env['akshab.stock.turnover.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, self.product.ids)],
            'date_from': self.now - timedelta(days=90), 'coverage_days': 90})
        data = wizard._build_report_data()
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['opening_qty'], 100.0, places=2)
        self.assertAlmostEqual(row['qty'], 70.0, places=2)
        self.assertAlmostEqual(row['sales_qty'], 30.0, places=2)
        self.assertGreater(row['cogs'], 0.0)
        self.assertAlmostEqual(row['avg_inventory'], (row['opening_value'] + row['value']) / 2.0, places=2)
        self.assertAlmostEqual(row['turnover'], row['cogs'] / row['avg_inventory'], places=4)
        self.assertAlmostEqual(row['dsi'], data['meta']['period_days'] / row['turnover'], places=2)
        self.assertAlmostEqual(row['coverage'], row['qty'] / row['avg_daily_cov'], places=2)

    def test_06_no_business_data_is_modified(self):
        """Building and exporting every report leaves stock / product / valuation tables untouched."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 10, 5)
        self.env.flush_all()

        def snapshot():
            out = {}
            for table in ('stock_move', 'stock_move_line', 'stock_quant', 'stock_valuation_layer', 'product_product'):
                self.env.cr.execute("SELECT COUNT(*), COALESCE(SUM(id), 0) FROM %s" % table)
                out[table] = self.env.cr.fetchone()
            self.env.cr.execute("SELECT SUM(quantity) FROM stock_quant")
            out['quant_qty'] = self.env.cr.fetchone()[0]
            self.env.cr.execute("SELECT MAX(write_date) FROM stock_move")
            out['move_write'] = self.env.cr.fetchone()[0]
            return out

        before = snapshot()
        for model in ('akshab.stock.report.wizard', 'akshab.stock.aging.wizard',
                      'akshab.stock.turnover.wizard', 'akshab.stock.status.wizard'):
            wizard = self.env[model].create({})
            wizard._build_report_data()
            wizard.action_export_xlsx()
        self.env.flush_all()
        self.assertEqual(before, snapshot())

    def test_07_sale_price_is_net_of_included_vat(self):
        """A 15% price-included VAT is stripped from the list price used for expected cash."""
        tax_vals = {'name': 'AKS VAT 15% incl', 'amount': 15.0, 'amount_type': 'percent', 'type_tax_use': 'sale',
                    'company_id': self.company.id}
        Tax = self.env['account.tax']
        if 'price_include_override' in Tax._fields:
            tax_vals['price_include_override'] = 'tax_included'
        else:  # older API
            tax_vals['price_include'] = True
        tax = Tax.create(tax_vals)
        product = self.env['product.product'].create({
            'name': 'AKS VAT Product', 'type': 'consu', 'is_storable': True, 'categ_id': self.categ.id,
            'standard_price': 50.0, 'list_price': 115.0, 'taxes_id': [(6, 0, tax.ids)]})
        self._move(product, self.supplier_loc, self.stock_loc, 10, 5)
        wizard = self.env['akshab.stock.report.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, product.ids)]})
        row = self._row(wizard._build_report_data(), product)
        self.assertAlmostEqual(row['price'], 100.0, places=2)
        self.assertAlmostEqual(row['price_incl'], 115.0, places=2)
        self.assertAlmostEqual(row['sale_value'], 1000.0, places=2)

    def _aging_data(self, product):
        wizard = self.env['akshab.stock.aging.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, product.ids)],
            'bucket_mode': 'step', 'bucket_days': 30, 'bucket_count': 6})
        return wizard._build_report_data()

    def test_08_negative_stock_rule(self):
        """Bought 100 in May, sold 200 today -> nothing to age (the negative balance never enters
        the report); then a purchase of 200 arrives -> only 100 is aged, from the purchase date."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 100, 121)   # May
        self._move(self.product, self.stock_loc, self.customer_loc, 200, 10)    # sold 200 -> balance -100
        data = self._aging_data(self.product)
        row = self._row(data, self.product)
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['qty'], 0.0, places=2)                       # nothing on hand to age
        self.assertAlmostEqual(row['neg_qty'], 100.0, places=2)
        self.assertAlmostEqual(row['net_qty'], self.product.with_context(warehouse_id=self.warehouse.id).qty_available, places=2)
        self.assertAlmostEqual(sum(row['bucket_qty']), 0.0, places=2)
        self.assertAlmostEqual(row['value'], 0.0, places=2)
        self.assertAlmostEqual(data['kpi']['total_value'], 0.0, places=2)
        self.assertAlmostEqual(data['kpi']['total_qty'], 0.0, places=2)
        self.assertEqual(data['kpi']['product_count'], 0)
        self.assertNotIn(self.product.id, [r['id'] for r in data['stocked']])

        # the purchase of 200 covers the negative 100 first: 100 aged from the purchase date
        self._move(self.product, self.supplier_loc, self.stock_loc, 200, 5)
        data = self._aging_data(self.product)
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['qty'], 100.0, places=2)
        self.assertAlmostEqual(row['neg_qty'], 0.0, places=2)
        self.assertAlmostEqual(row['bucket_qty'][0], 100.0, places=2)           # 0-30 days (the purchase)
        self.assertAlmostEqual(sum(row['bucket_qty'][1:]), 0.0, places=2)      # nothing left from May
        self.assertLessEqual(row['max_age'], 6)
        self.assertAlmostEqual(data['kpi']['total_qty'], 100.0, places=2)

    def test_09_branch_negative_kept_apart_from_positive_branch(self):
        """+20 in one branch and -5 in another: only the 20 are aged and valued; the -5 never
        enter any figure; net = Odoo's on hand."""
        Warehouse = self.env['stock.warehouse']
        code = next(c for c in ('AKST', 'AKS2', 'AKS3', 'AKS4') if not Warehouse.search([('code', '=', c)], limit=1))
        other = Warehouse.create({'name': 'AKS Test WH', 'code': code, 'company_id': self.company.id})
        self._move(self.product, self.supplier_loc, self.stock_loc, 20, 40)
        self._move(self.product, other.lot_stock_id, self.customer_loc, 5, 3)   # sale from the empty branch
        wizard = self.env['akshab.stock.aging.wizard'].create({
            'warehouse_ids': [(6, 0, (self.warehouse + other).ids)], 'product_ids': [(6, 0, self.product.ids)]})
        data = wizard._build_report_data()
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['qty'], 20.0, places=2)
        self.assertAlmostEqual(row['neg_qty'], 5.0, places=2)
        self.assertAlmostEqual(row['net_qty'], 15.0, places=2)
        self.assertAlmostEqual(row['net_qty'], self.product.qty_available, places=2)
        self.assertAlmostEqual(sum(row['bucket_qty']), 20.0, places=2)
        self.assertAlmostEqual(row['value'], 20.0 * row['unit_cost'], places=2)
        self.assertEqual(row['wh_qty'], {self.warehouse.id: 20.0})
        self.assertAlmostEqual(data['kpi']['total_qty'], 20.0, places=2)
        self.assertAlmostEqual(sum(b['qty'] for b in data['aging']['buckets']), 20.0, places=2)
        # the aging by warehouse only carries the positive branch; the negative one appears nowhere
        self.assertEqual([r['key'] for r in data['aging_by_warehouse']['rows']], [self.warehouse.id])
        self.assertNotIn('AKS Test WH', row['wh_text'])
        html = self.env['ir.actions.report']._render_qweb_html('akshab_stock_report.report_aging_doc', wizard.ids)[0]
        self.assertTrue(html)
        wizard.action_export_xlsx()
        self.assertTrue(wizard.xlsx_file)

    def test_10_status_report_unsold_items(self):
        """Item-status report: a never-sold item is stagnant (no "new" status); it is only put under
        watch (no liquidation) while it is younger than the stagnation window, and recommended for
        a discount once older."""
        recent = self.env['product.product'].create({
            'name': 'AKS Recent Product', 'type': 'consu', 'is_storable': True, 'categ_id': self.categ.id,
            'standard_price': 10.0, 'list_price': 25.0})
        self._move(recent, self.supplier_loc, self.stock_loc, 10, 20)        # received 20 days ago, never sold
        self._move(self.product, self.supplier_loc, self.stock_loc, 10, 120)  # received 120 days ago, never sold
        wizard = self.env['akshab.stock.status.wizard'].create({
            'warehouse_ids': [(6, 0, self.warehouse.ids)], 'product_ids': [(6, 0, (recent + self.product).ids)],
            'stagnant_days': 90})
        data = wizard._build_report_data()
        self.assertNotIn('new', [s['key'] for s in data['status_summary']])
        r_recent = self._row(data, recent)
        r_old = self._row(data, self.product)
        self.assertEqual(r_recent['status'], 'stagnant')
        self.assertEqual(r_recent['action'], 'watch')
        self.assertAlmostEqual(r_recent['liq_qty'], 0.0, places=2)
        self.assertEqual(r_old['status'], 'stagnant')
        self.assertEqual(r_old['action'], 'discount')
        self.assertAlmostEqual(r_old['liq_qty'], 10.0, places=2)
        self.assertAlmostEqual(data['plan']['total']['qty'], 10.0, places=2)   # only the old one is in the plan

    def test_11_company_access_is_checked(self):
        """A user cannot build a report for a company they do not belong to."""
        other = self.env['res.company'].create({'name': 'AKS Other Co'})
        user = self.env['res.users'].create({
            'name': 'AKS Stock User', 'login': 'aks_stock_user_%d' % self.company.id,
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('stock.group_stock_user').id])]})
        wizard = self.env['akshab.stock.aging.wizard'].with_user(user).create({'company_id': self.company.id})
        self.assertIn('kpi', wizard._build_report_data())
        wizard_other = self.env['akshab.stock.aging.wizard'].with_user(user).sudo().create({'company_id': other.id}).with_user(user)
        with self.assertRaises(AccessError):
            wizard_other._build_report_data()

    def test_12_dashboard_data_and_actions(self):
        """The dashboard backend: defaults, data with previous-period comparison, trend, report actions."""
        self._move(self.product, self.supplier_loc, self.stock_loc, 60, 120)
        self._move(self.product, self.stock_loc, self.customer_loc, 20, 30)
        Dash = self.env['akshab.stock.dashboard']
        defaults = Dash.get_filter_defaults()
        self.assertEqual(defaults['filters']['company_id'], self.company.id)
        filters = dict(defaults['filters'], warehouse_ids=self.warehouse.ids, product_ids=self.product.ids)
        data = Dash.get_dashboard_data(filters)
        for key in ('meta', 'kpi', 'previous', 'compare', 'status_summary', 'aging', 'warehouses', 'categories',
                    'turnover', 'lists', 'plan', 'totals', 'insights'):
            self.assertIn(key, data)
        self.assertAlmostEqual(data['kpi']['total_qty'], 40.0, places=2)
        self.assertAlmostEqual(data['compare']['total_qty']['previous'], 60.0, places=2)   # stock at the period start
        self.assertAlmostEqual(data['compare']['total_qty']['delta'], -20.0, places=2)
        self.assertNotIn('new', [s['key'] for s in data['status_summary']])
        self.assertEqual(data['meta']['period_days'], 90)
        self.assertEqual(len(data['aging']['buckets']), 7)
        # JSON-safe payload
        import json
        json.dumps(data)
        trend = Dash.get_trend(filters, 2, 30)
        self.assertEqual(len(trend['points']), 2)
        json.dumps(trend)
        # the report wizards open with the dashboard filters
        for kind, model in (('full', 'akshab.stock.report.wizard'), ('aging', 'akshab.stock.aging.wizard'),
                            ('turnover', 'akshab.stock.turnover.wizard'), ('status', 'akshab.stock.status.wizard')):
            action = Dash.action_open_report(kind, 'form', filters)
            self.assertEqual(action['res_model'], model)
            wizard = self.env[model].browse(action['res_id'])
            self.assertEqual(wizard.warehouse_ids, self.warehouse)
            self.assertEqual(wizard.product_ids, self.product)
            self.assertEqual(Dash.action_open_report(kind, 'pdf', filters)['type'], 'ir.actions.report')
            self.assertEqual(Dash.action_open_report(kind, 'xlsx', filters)['type'], 'ir.actions.act_url')
        # invalid filters are rejected cleanly
        with self.assertRaises(UserError):
            Dash.get_dashboard_data(dict(filters, date_from=filters['date_to']))
        with self.assertRaises(UserError):
            Dash.get_dashboard_data(dict(filters, bucket_mode='custom', bucket_1=90, bucket_2=30))

    def test_13_dashboard_access(self):
        """Only inventory users / accountants can use the dashboard, and only for their companies."""
        plain = self.env['res.users'].create({
            'name': 'AKS Plain User', 'login': 'aks_plain_%d' % self.company.id,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            self.env['akshab.stock.dashboard'].with_user(plain).get_filter_defaults()
        other = self.env['res.company'].create({'name': 'AKS Other Co 2'})
        stock_user = self.env['res.users'].create({
            'name': 'AKS Stock User 2', 'login': 'aks_stock2_%d' % self.company.id,
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('stock.group_stock_user').id])]})
        Dash = self.env['akshab.stock.dashboard'].with_user(stock_user)
        filters = Dash.get_filter_defaults()['filters']
        self.assertIn('kpi', Dash.get_dashboard_data(filters))
        with self.assertRaises(AccessError):
            Dash.get_dashboard_data(dict(filters, company_id=other.id))

    def test_14_aging_scope_vs_branch(self):
        """Replica of the real AKSH-BSIG-002 case (QRW / MKH / 3PL / 3PL-JED + packaging output).

        Default (aging_scope='scope'): age counts from entry into the SELECTED scope, so the
        internal transfers between the four warehouses never reset the age — all 975 remaining
        units belong to the two supplier receipts (175 / 174 days ago) and land in 151-180.
        Secondary option (aging_scope='branch'): each warehouse's own receipts set the age."""
        Warehouse = self.env['stock.warehouse']

        def make_wh(name, base):
            code = next(c for c in (base + '1', base + '2', base + '3', base + '4')
                        if not Warehouse.search([('code', '=', c)], limit=1))
            return Warehouse.create({'name': name, 'code': code, 'company_id': self.company.id})

        tpl = make_wh('AKS 3PL', 'AKP')
        tjed = make_wh('AKS 3PL-JED', 'AKJ')
        mkh = make_wh('AKS MKH', 'AKM')
        prod_loc = self.env['stock.location'].search([('usage', '=', 'production')], limit=1)
        if not prod_loc:
            prod_loc = self.env['stock.location'].create({'name': 'AKS Production', 'usage': 'production'})
        p = self.env['product.product'].create({
            'name': 'AKS Box Small Incense', 'type': 'consu', 'is_storable': True, 'categ_id': self.categ.id,
            'standard_price': 27.62, 'list_price': 55.0})
        qrw_loc, tpl_loc, tjed_loc, mkh_loc = self.stock_loc, tpl.lot_stock_id, tjed.lot_stock_id, mkh.lot_stock_id
        # the real move history (12 moves; the three 0-qty receipts are irrelevant)
        self._move(p, self.supplier_loc, qrw_loc, 50, 175)      # QRW/IN/00252
        self._move(p, self.supplier_loc, tpl_loc, 950, 174)     # QRW/IN/00253 -> 3PL
        self._move(p, tpl_loc, qrw_loc, 42, 133)                # QRW/INT/00325
        self._move(p, tpl_loc, tjed_loc, 200, 115)              # 3PL-JED/INT/00001
        self._move(p, tjed_loc, mkh_loc, 10, 102)               # MKH/INT/00001
        self._move(p, tjed_loc, mkh_loc, 7, 54)                 # QRW/INT/00371
        self._move(p, qrw_loc, prod_loc, 22, 34)                # Packaging Output/00012
        self._move(p, mkh_loc, prod_loc, 3, 34)                 # Packaging Output/00016
        self._move(p, tpl_loc, qrw_loc, 8, 5)                   # QRW/INT/00391

        wh_qty = {self.warehouse.id: 78.0, mkh.id: 14.0, tpl.id: 700.0, tjed.id: 183.0}

        # ---- default: scope mode — the internal transfers never reset the age --------------
        wizard = self.env['akshab.stock.aging.wizard'].create({
            'warehouse_ids': [(6, 0, (self.warehouse + mkh + tpl + tjed).ids)],
            'product_ids': [(6, 0, p.ids)], 'bucket_mode': 'step', 'bucket_days': 30, 'bucket_count': 6})
        self.assertEqual(wizard.aging_scope, 'scope')
        data = wizard._build_report_data()
        row = self._row(data, p)
        self.assertAlmostEqual(row['qty'], 975.0, places=2)
        self.assertEqual(row['wh_qty'], wh_qty)
        self.assertEqual([round(q) for q in row['bucket_qty']], [0, 0, 0, 0, 0, 975, 0])
        self.assertEqual(round(row['max_age']), 175)
        self.assertEqual(data['meta']['aging_scope'], 'scope')
        # by-warehouse table: the branch quantities, all in the same scope-level bucket
        by_wh = {r['key']: r for r in data['aging_by_warehouse']['rows']}
        for wh_id, q in wh_qty.items():
            self.assertEqual([round(x) for x in by_wh[wh_id]['qty']],
                             [0, 0, 0, 0, 0, round(q), 0])
        for i in range(7):
            self.assertAlmostEqual(sum(r['qty'][i] for r in by_wh.values()), row['bucket_qty'][i], places=2)
        self.assertAlmostEqual(data['aging_by_warehouse']['total_qty'], 975.0, places=2)
        self.assertAlmostEqual(data['aging_by_warehouse']['total'], data['kpi']['total_value'], places=2)
        self.assertAlmostEqual(sum(by_wh[w]['total'] for w in by_wh), data['kpi']['total_value'], places=2)

        # ---- secondary option: branch mode — every transfer starts a new age in the branch --
        wizard_b = self.env['akshab.stock.aging.wizard'].create({
            'warehouse_ids': [(6, 0, (self.warehouse + mkh + tpl + tjed).ids)],
            'product_ids': [(6, 0, p.ids)], 'bucket_mode': 'step', 'bucket_days': 30, 'bucket_count': 6,
            'aging_scope': 'branch'})
        data_b = wizard_b._build_report_data()
        row_b = self._row(data_b, p)
        self.assertAlmostEqual(row_b['qty'], 975.0, places=2)
        self.assertEqual(row_b['wh_qty'], wh_qty)
        self.assertEqual([round(q) for q in row_b['bucket_qty']], [8, 7, 0, 190, 42, 728, 0])
        self.assertEqual(data_b['meta']['aging_scope'], 'branch')
        # each branch keeps its own receipt ages
        by_wh_b = {r['key']: r for r in data_b['aging_by_warehouse']['rows']}
        self.assertEqual([round(q) for q in by_wh_b[tpl.id]['qty']], [0, 0, 0, 0, 0, 700, 0])
        self.assertEqual([round(q) for q in by_wh_b[self.warehouse.id]['qty']], [8, 0, 0, 0, 42, 28, 0])
        self.assertEqual([round(q) for q in by_wh_b[tjed.id]['qty']], [0, 0, 0, 183, 0, 0, 0])
        self.assertEqual([round(q) for q in by_wh_b[mkh.id]['qty']], [0, 7, 0, 7, 0, 0, 0])
        for i in range(7):
            self.assertAlmostEqual(sum(r['qty'][i] for r in by_wh_b.values()), row_b['bucket_qty'][i], places=2)
        self.assertAlmostEqual(data_b['aging_by_warehouse']['total_qty'], 975.0, places=2)
        self.assertAlmostEqual(data_b['aging_by_warehouse']['total'], data_b['kpi']['total_value'], places=2)

    def test_15_active_only_and_location_without_warehouse(self):
        """Archived products never appear; an internal location that belongs to no warehouse is
        shown under its own name (no parent path, no "without warehouse")."""
        archived = self.env['product.product'].create({
            'name': 'AKS Archived Product', 'type': 'consu', 'is_storable': True, 'categ_id': self.categ.id,
            'standard_price': 5.0, 'list_price': 9.0})
        self._move(archived, self.supplier_loc, self.stock_loc, 7, 10)
        archived.action_archive()
        parent = self.env['stock.location'].create({'name': 'AKS Parent', 'usage': 'view', 'company_id': self.company.id})
        free_loc = self.env['stock.location'].create({
            'name': 'AKS Free Room', 'usage': 'internal', 'location_id': parent.id, 'company_id': self.company.id})
        self.assertFalse(free_loc.warehouse_id)
        self._move(self.product, self.supplier_loc, self.stock_loc, 4, 30)
        self._move(self.product, self.supplier_loc, free_loc, 6, 20)
        wizard = self.env['akshab.stock.report.wizard'].create({'product_ids': [(6, 0, (self.product + archived).ids)]})
        data = wizard._build_report_data()
        self.assertIsNone(self._row(data, archived))
        row = self._row(data, self.product)
        self.assertAlmostEqual(row['qty'], 10.0, places=2)
        self.assertIn('AKS Free Room: 6', row['wh_text'])
        self.assertNotIn('AKS Parent/', row['wh_text'])
        self.assertNotIn('بدون مستودع', row['wh_text'])
        self.assertIn('AKS Free Room', [w['name'] for w in data['by_warehouse']])
        self.assertTrue(row['display_name'].endswith('AKS Test Product'))
        self.assertIn('[AKS-T1]', row['display_name'])

    def test_16_category_order_is_fixed(self):
        """Categories are listed in the order management reads them, whatever their value;
        a category outside the list comes after all of them."""
        Categ = self.env['product.category']
        names = ['Premium Packaging', 'Incense', 'Marketing products', 'Perfume', 'ZZ Unlisted Categ']
        cats = {}
        for i, name in enumerate(names):
            cats[name] = Categ.create({'name': name, 'property_cost_method': 'average',
                                       'property_valuation': 'manual_periodic'})
            p = self.env['product.product'].create({
                'name': 'AKS Ord %d' % i, 'type': 'consu', 'is_storable': True, 'categ_id': cats[name].id,
                'standard_price': 10.0 * (i + 1), 'list_price': 25.0 * (i + 1)})
            self._move(p, self.supplier_loc, self.stock_loc, 10 * (i + 1), 30)
        wizard = self.env['akshab.stock.report.wizard'].create({
            'categ_ids': [(6, 0, [c.id for c in cats.values()])]})
        data = wizard._build_report_data()
        order = [c['name'] for c in data['by_category']]
        self.assertEqual(order, ['Incense', 'Perfume', 'Premium Packaging', 'Marketing products', 'ZZ Unlisted Categ'])
        self.assertEqual([r['name'] for r in data['aging_by_category']['rows']], order)
        groups = [g['name'] for g in data['status_groups']['stagnant']['groups']]
        self.assertEqual(groups, [n for n in order if n in groups])
