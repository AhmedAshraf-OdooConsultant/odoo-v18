# -*- coding: utf-8 -*-
"""Inventory performance dashboard – backend.

The OWL client action ``akshab_stock_dashboard`` calls the ``@api.model`` methods of this
transient model.  Everything is read-only: the engine of the four reports is run with the
filters sent by the browser and the result is serialised to plain JSON.  A second engine run
"as of" the start of the period gives the previous-period comparison, and ``get_trend`` runs
the engine at several past dates for the trend charts.
"""
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from ..report.stock_report_engine import (
    ReportOptions, StockReportEngine, STATUS_LABELS, ACTION_LABELS, COST_BASIS_LABELS, COGS_BASIS_LABELS,
)

DASHBOARD_GROUPS = ('stock.group_stock_user', 'account.group_account_invoice')

# product-row keys copied to the browser (everything else stays server side)
ROW_KEYS = (
    'id', 'name', 'name_ltr', 'code', 'category', 'categ_id', 'uom', 'archived', 'qty', 'value', 'unit_cost', 'price',
    'sale_value', 'margin_pct', 'max_discount', 'sales_qty', 'avg_daily', 'cover_days', 'coverage', 'avg_daily_cov',
    'last_sale_str', 'days_since_sale', 'first_receipt_str', 'last_receipt_str', 'incoming_qty', 'bucket_qty',
    'bucket_value', 'avg_age', 'max_age', 'status', 'status_label', 'excess_qty', 'excess_value', 'opening_qty',
    'opening_value', 'cogs', 'avg_inventory', 'turnover', 'turnover_annual', 'dsi', 'action', 'action_label',
    'action_text', 'applied_discount', 'liq_qty', 'liq_cost', 'liq_sale_value', 'expected_cash', 'wh_text',
)
CATEGORY_KEYS = (
    'name', 'name_ltr', 'categ_id', 'count', 'count_all', 'qty', 'value', 'pct', 'sale_value', 'bucket_qty', 'bucket_value',
    'bucket_pct', 'last_qty', 'last_value', 'last_pct', 'avg_age', 'max_age', 'active_value', 'active_count',
    'slow_value', 'slow_count', 'stagnant_value', 'stagnant_pct', 'stagnant_count', 'sales_qty', 'cov_sales_qty',
    'avg_daily', 'avg_daily_cov', 'coverage', 'opening_qty', 'opening_value', 'cogs', 'avg_inventory', 'turnover',
    'turnover_annual', 'dsi',
)
WAREHOUSE_KEYS = (
    'id', 'name', 'count', 'qty', 'value', 'pct', 'active_value', 'slow_value', 'stagnant_value', 'stagnant_pct',
    'stagnant_count', 'idle_count', 'idle_value', 'avg_age', 'sales_qty', 'turnover', 'dsi',
)
TRANSFER_KEYS = (
    'product', 'name_ltr', 'category', 'from_id', 'from_name', 'from_qty', 'from_days_no_sale', 'to_id', 'to_name',
    'to_qty', 'to_avg_daily', 'to_cover', 'qty', 'value', 'unit_cost',
)


def _pick(d, keys):
    out = {}
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, dict):
                v = {str(kk): vv for kk, vv in v.items()}
            out[k] = v
    return out


class AkshabStockDashboard(models.TransientModel):
    _name = 'akshab.stock.dashboard'
    _description = 'Akshab Inventory Performance Dashboard'

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    @api.model
    def _check_dashboard_access(self, company):
        user = self.env.user
        if not self.env.su and not any(user.has_group(g) for g in DASHBOARD_GROUPS):
            raise AccessError(_('لوحة أداء المخزون متاحة لمستخدمي المخزون وفريق المحاسبة فقط.'))
        if not self.env.su and company not in user.company_ids:
            raise AccessError(_('لا تملك صلاحية عرض بيانات الشركة %s.') % company.sudo().display_name)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    @api.model
    def get_filter_defaults(self):
        """Defaults + reference data for the filter bar."""
        company = self.env.company
        self._check_dashboard_access(company)
        now = fields.Datetime.now().replace(microsecond=0)
        companies = self.env.user.company_ids.sudo()
        warehouses = self.env['stock.warehouse'].search_read(
            [('company_id', 'in', companies.ids)], ['id', 'name', 'code', 'company_id'], order='sequence, id')
        return {
            'filters': {
                'company_id': company.id,
                'date_to': fields.Datetime.to_string(now),
                'date_from': fields.Datetime.to_string(now - timedelta(days=90)),
                'warehouse_ids': [],
                'location_ids': [],
                'categ_ids': [],
                'product_ids': [],
                'cost_basis': 'svl',
                'cogs_basis': 'svl',
                'aging_scope': 'scope',
                'coverage_days': 90,
                'stagnant_days': 90,
                'slow_cover_days': 180,
                'reorder_cover_days': 15,
                'liquidation_discount': 30.0,
                'bucket_mode': 'step',
                'bucket_days': 30,
                'bucket_count': 6,
                'bucket_1': 30, 'bucket_2': 60, 'bucket_3': 90, 'bucket_4': 180, 'bucket_5': 365,
                'top_n': 10,
            },
            'companies': [{'id': c.id, 'name': c.name} for c in companies],
            'warehouses': [{'id': w['id'], 'name': w['name'], 'code': w['code'], 'company_id': w['company_id'][0]}
                           for w in warehouses],
            'labels': {
                'cost_basis': COST_BASIS_LABELS,
                'cogs_basis': COGS_BASIS_LABELS,
                'status': STATUS_LABELS,
                'action': ACTION_LABELS,
            },
            'user_tz': self.env.user.tz or 'UTC',
        }

    # ------------------------------------------------------------------
    @api.model
    def _parse_filters(self, f):
        """Validate the browser payload and turn it into (company, cleaned dict)."""
        f = dict(f or {})
        company = self.env['res.company'].browse(int(f.get('company_id') or self.env.company.id))
        if not company.exists():
            raise UserError(_('الشركة غير موجودة.'))
        self._check_dashboard_access(company)

        def _int(key, default, lo=None, hi=None):
            try:
                v = int(f.get(key, default) if f.get(key) not in (None, '') else default)
            except (TypeError, ValueError):
                raise UserError(_('قيمة غير صحيحة للحقل %s.') % key)
            if lo is not None and v < lo or hi is not None and v > hi:
                raise UserError(_('قيمة الحقل %s خارج النطاق المسموح.') % key)
            return v

        def _float(key, default, lo=None, hi=None):
            try:
                v = float(f.get(key, default) if f.get(key) not in (None, '') else default)
            except (TypeError, ValueError):
                raise UserError(_('قيمة غير صحيحة للحقل %s.') % key)
            if lo is not None and v < lo or hi is not None and v > hi:
                raise UserError(_('قيمة الحقل %s خارج النطاق المسموح.') % key)
            return v

        def _ids(key, model, extra_domain=None):
            ids = [int(x) for x in (f.get(key) or []) if x]
            if not ids:
                return self.env[model]
            domain = [('id', 'in', ids)] + (extra_domain or [])
            return self.env[model].with_context(active_test=False).search(domain)

        date_to = fields.Datetime.to_datetime(f.get('date_to')) or fields.Datetime.now()
        date_from = fields.Datetime.to_datetime(f.get('date_from')) or (date_to - timedelta(days=90))
        if date_from >= date_to:
            raise UserError(_('بداية الفترة يجب أن تسبق تاريخ المخزون (نهاية الفترة).'))
        if (date_to - date_from).days > 3660:
            raise UserError(_('الفترة لا يمكن أن تتجاوز عشر سنوات.'))

        bucket_mode = f.get('bucket_mode') if f.get('bucket_mode') in ('step', 'custom') else 'step'
        if bucket_mode == 'step':
            days = _int('bucket_days', 30, 1, 3650)
            count = _int('bucket_count', 6, 1, 24)
            buckets = [days * i for i in range(1, count + 1)]
        else:
            buckets = [_int('bucket_%d' % i, d, 1, 36500) for i, d in ((1, 30), (2, 60), (3, 90), (4, 180), (5, 365))]
            if any(buckets[i] >= buckets[i + 1] for i in range(4)):
                raise UserError(_('يجب أن تكون حدود الفئات العمرية أرقاماً موجبة ومتصاعدة.'))

        clean = {
            'company': company,
            'date_to': date_to,
            'date_from': date_from,
            'warehouse_ids': _ids('warehouse_ids', 'stock.warehouse', [('company_id', '=', company.id)]),
            'location_ids': _ids('location_ids', 'stock.location', [('company_id', '=', company.id), ('usage', '=', 'internal')]),
            'categ_ids': _ids('categ_ids', 'product.category'),
            'product_ids': _ids('product_ids', 'product.product'),
            'cost_basis': f.get('cost_basis') if f.get('cost_basis') in ('svl', 'standard') else 'svl',
            'cogs_basis': f.get('cogs_basis') if f.get('cogs_basis') in ('svl', 'unit_cost') else 'svl',
            'aging_scope': f.get('aging_scope') if f.get('aging_scope') in ('scope', 'branch') else 'scope',
            'coverage_days': _int('coverage_days', 90, 1, 3650),
            'stagnant_days': _int('stagnant_days', 90, 1, 3650),
            'slow_cover_days': _int('slow_cover_days', 180, 1, 36500),
            'reorder_cover_days': _int('reorder_cover_days', 15, 0, 3650),
            'liquidation_discount': _float('liquidation_discount', 30.0, 0.0, 99.0),
            'buckets': buckets,
            'bucket_mode': bucket_mode,
            'bucket_days': _int('bucket_days', 30, 1, 3650),
            'bucket_count': _int('bucket_count', 6, 1, 24),
            'top_n': _int('top_n', 10, 1, 200),
        }
        return clean

    @api.model
    def _options(self, c, date_to=None, date_from=None):
        return ReportOptions(
            company=c['company'],
            date_to=date_to or c['date_to'],
            date_from=date_from or c['date_from'],
            warehouse_ids=c['warehouse_ids'],
            location_ids=c['location_ids'],
            categ_ids=c['categ_ids'],
            product_ids=c['product_ids'],
            coverage_days=c['coverage_days'],
            stagnant_days=c['stagnant_days'],
            new_days=0,                       # like the item-status report: no "new" status
            slow_cover_days=c['slow_cover_days'],
            reorder_cover_days=c['reorder_cover_days'],
            liquidation_discount=c['liquidation_discount'],
            cost_basis=c['cost_basis'],
            cogs_basis=c['cogs_basis'],
            aging_scope=c['aging_scope'],
            buckets=c['buckets'],
            old_days=c['buckets'][-1],
            top_n=c['top_n'],
            max_lines=0,
        )

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    @api.model
    def _kpi_snapshot(self, d):
        """The handful of headline figures used for comparisons and trends."""
        k, tl = d['kpi'], d['turnover_lists']
        return {
            'total_value': k['total_value'],
            'total_qty': k['total_qty'],
            'total_sale_value': k['total_sale_value'],
            'product_count': k['product_count'],
            'active_value': k['active_value'], 'active_pct': k['active_pct'], 'active_count': k['active_count'],
            'slow_value': k['slow_value'], 'slow_pct': k['slow_pct'], 'slow_count': k['slow_count'],
            'stagnant_value': k['stagnant_value'], 'stagnant_pct': k['stagnant_pct'], 'stagnant_count': k['stagnant_count'],
            'last_value': k['last_value'], 'last_pct': k['last_pct'], 'last_qty': k['last_qty'],
            'max_age': k['max_age'],
            'avg_age': k['avg_age'],
            'turnover_annual': k['turnover_annual'] or 0.0,
            'turnover_period': k['turnover_period'] or 0.0,
            'dsi': k['dsi'],
            'coverage': k['coverage'],
            'cogs': k['cogs_window'],
            'sales_qty': k['sales_qty'],
            'opening_value': k['opening_value'],
            'avg_inventory': k['avg_inventory'],
            'health_score': k['health_score'], 'health_label': k['health_label'],
            'out_count': k['out_count'],
            'reorder_count': k['reorder_count'],
            'transfer_count': k['transfer_count'], 'transfer_value': k['transfer_value'],
            'no_turnover_count': tl['none_count'], 'no_turnover_value': tl['none_value'], 'no_turnover_pct': tl['none_pct'],
            'expected_cash': k['expected_cash'], 'stagnant_cash': k['stagnant_cash'],
        }

    @api.model
    def get_dashboard_data(self, filters):
        c = self._parse_filters(filters)
        eng = StockReportEngine(self, self._options(c))
        d = eng.build()
        period_days = d['meta']['period_days']

        # previous period: same length, ending where the current one starts
        prev_to = c['date_from']
        prev_from = prev_to - timedelta(days=period_days)
        prev = StockReportEngine(self, self._options(c, date_to=prev_to, date_from=prev_from)).build()

        cur_k = self._kpi_snapshot(d)
        prev_k = self._kpi_snapshot(prev)
        compare = {}
        for key, val in cur_k.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                pv = prev_k.get(key)
                pv = float(pv) if isinstance(pv, (int, float)) and not isinstance(pv, bool) else None
                delta = (val - pv) if pv is not None else None
                compare[key] = {'current': val, 'previous': pv, 'delta': delta,
                                'delta_pct': (delta / pv * 100.0) if pv else None}

        # previous per-branch / per-category stock value (for the comparison columns)
        prev_wh = {w['id']: w for w in prev['by_warehouse']}
        prev_cat = {cat['name']: cat for cat in prev['by_category']}
        warehouses = []
        for w in d['by_warehouse']:
            row = _pick(w, WAREHOUSE_KEYS)
            pw = prev_wh.get(w['id'])
            row['prev_value'] = pw['value'] if pw else None
            row['prev_stagnant_pct'] = pw['stagnant_pct'] if pw else None
            row['prev_turnover'] = pw['turnover'] if pw else None
            warehouses.append(row)
        wh_aging = {r['key']: r for r in d['aging_by_warehouse']['rows']}
        for row in warehouses:
            ag = wh_aging.get(row['id'])
            row['bucket_value'] = ag['values'] if ag else [0.0] * d['meta']['n_buckets']
            row['bucket_qty'] = ag['qty'] if ag else [0.0] * d['meta']['n_buckets']
            row['last_pct'] = ag['pct_last'] if ag else 0.0
        categories = []
        for cat in d['by_category']:
            row = _pick(cat, CATEGORY_KEYS)
            pc = prev_cat.get(cat['name'])
            row['prev_value'] = pc['value'] if pc else None
            row['prev_stagnant_pct'] = pc['stagnant_pct'] if pc else None
            row['prev_turnover_annual'] = pc['turnover_annual'] if pc else None
            row['prev_sales_qty'] = pc['sales_qty'] if pc else None
            categories.append(row)

        rows = lambda items, n=None: [_pick(r, ROW_KEYS) for r in (items[:n] if n else items)]  # noqa: E731
        top_n = c['top_n']
        tl = d['turnover_lists']
        m = d['meta']
        return {
            'meta': {
                'company_name': m['company_name'],
                'currency': m['currency'],
                'date_to_display': m['date_to_display'],
                'date_to_date': m['date_to_date'],
                'date_from_date': m['date_from_date'],
                'prev_from_date': prev['meta']['date_from_date'],
                'prev_to_date': prev['meta']['date_to_date'],
                'period_days': period_days,
                'coverage_days': m['coverage_days'],
                'coverage_from': m['coverage_from'],
                'mode': m['mode'],
                'mode_label': m['mode_label'],
                'warehouses_display': m['warehouses_display'],
                'locations_display': m['locations_display'],
                'categories_display': m['categories_display'],
                'products_display': m['products_display'],
                'bucket_labels': m['bucket_labels'],
                'buckets': m['buckets'],
                'n_buckets': m['n_buckets'],
                'last_label': m['last_label'],
                'last_days': m['last_days'],
                'stagnant_days': m['stagnant_days'],
                'slow_cover_days': m['slow_cover_days'],
                'reorder_cover_days': m['reorder_cover_days'],
                'liquidation_discount': m['liquidation_discount'],
                'cost_basis_label': m['cost_basis_label'],
                'cogs_basis_label': m['cogs_basis_label'],
                'aging_scope': m['aging_scope'],
                'aging_scope_label': m['aging_scope_label'],
                'wh_aging_hint': m['wh_aging_hint'],
                'multi_warehouse': m['multi_warehouse'],
                'warehouses': m['warehouses'],
                'top_n': top_n,
                'generated_at': m['print_date'],
            },
            'kpi': cur_k,
            'previous': prev_k,
            'compare': compare,
            'status_summary': [{k: v for k, v in s.items()} for s in d['status_summary']],
            'aging': {
                'buckets': [{'index': b['index'], 'label': b['label'], 'qty': b['qty'], 'value': b['value'],
                             'pct': b['pct'], 'pct_qty': b['pct_qty'], 'is_old': b['is_old']} for b in d['aging']['buckets']],
                'prev_buckets': [{'label': b['label'], 'value': b['value'], 'pct': b['pct']} for b in prev['aging']['buckets']],
                'by_category': [{'name': r['name'], 'values': r['values'], 'qty': r['qty'], 'total': r['total'],
                                 'pct_last': r['pct_last']} for r in d['aging_by_category']['rows']],
            },
            'warehouses': warehouses,
            'categories': categories,
            'turnover': {
                'top': rows(tl['top']),
                'bottom': rows(tl['bottom']),
                'none': rows(tl['none_all'], top_n),
                'none_count': tl['none_count'], 'none_value': tl['none_value'], 'none_pct': tl['none_pct'],
                'none_qty': tl['none_qty'],
            },
            'lists': {
                'stagnant': rows(d['stagnant'], top_n),
                'stagnant_count': len(d['stagnant']),
                'slow': rows(d['slow'], top_n),
                'slow_count': len(d['slow']),
                'active': rows(d['active'], top_n),
                'active_count': len(d['active']),
                'out': rows(d['out'], top_n),
                'out_count': len(d['out']),
                'reorder': rows(d['reorder'], top_n),
                'reorder_count': len(d['reorder']),
                'oldest': rows(d['oldest'], top_n),
                'transfers': [_pick(t, TRANSFER_KEYS) for t in d['transfers'][:top_n]],
                'transfers_count': len(d['transfers']),
            },
            'plan': {'rows': d['plan']['rows'], 'total': d['plan']['total']},
            'totals': {k: v for k, v in d['totals'].items() if isinstance(v, (int, float, str))},
            'insights': d['insights'],
        }

    @api.model
    def get_trend(self, filters, points=6, step_days=30):
        """Headline figures at ``points`` past dates (every ``step_days`` days back from date_to),
        each computed with the same period length as the current filters."""
        c = self._parse_filters(filters)
        points = max(2, min(int(points or 6), 24))
        step_days = max(7, min(int(step_days or 30), 365))
        period_days = max(1, (c['date_to'] - c['date_from']).days)
        out = []
        for i in range(points - 1, -1, -1):
            date_to = c['date_to'] - timedelta(days=step_days * i)
            date_from = date_to - timedelta(days=period_days)
            eng = StockReportEngine(self, self._options(c, date_to=date_to, date_from=date_from))
            d = eng.build()
            snap = self._kpi_snapshot(d)
            snap['date'] = d['meta']['date_to_date']
            snap['label'] = d['meta']['date_to_date']
            out.append(snap)
        return {'points': out, 'period_days': period_days, 'step_days': step_days}

    # ------------------------------------------------------------------
    # Open the report wizards with the dashboard filters
    # ------------------------------------------------------------------
    @api.model
    def action_open_report(self, kind, fmt, filters):
        """Create the wizard of ``kind`` (aging / turnover / status / full) with the dashboard
        filters and return the print (pdf) or export (xlsx) action."""
        c = self._parse_filters(filters)
        base_vals = {
            'company_id': c['company'].id,
            'date_to': c['date_to'],
            'warehouse_ids': [(6, 0, c['warehouse_ids'].ids)],
            'location_ids': [(6, 0, c['location_ids'].ids)],
            'categ_ids': [(6, 0, c['categ_ids'].ids)],
            'product_ids': [(6, 0, c['product_ids'].ids)],
            'cost_basis': c['cost_basis'],
            'aging_scope': c['aging_scope'],
        }
        b = c['buckets']
        five = (b + [b[-1] * 2, b[-1] * 4, b[-1] * 8, b[-1] * 16])[:5]
        period_days = max(1, (c['date_to'] - c['date_from']).days)
        if kind == 'aging':
            model = 'akshab.stock.aging.wizard'
            vals = dict(base_vals, bucket_mode=c['bucket_mode'], bucket_days=c['bucket_days'], bucket_count=c['bucket_count'],
                        bucket_1=five[0], bucket_2=five[1], bucket_3=five[2], bucket_4=five[3], bucket_5=five[4],
                        max_lines=0)
        elif kind == 'turnover':
            model = 'akshab.stock.turnover.wizard'
            vals = dict(base_vals, date_from=c['date_from'], coverage_days=c['coverage_days'], cogs_basis=c['cogs_basis'],
                        top_n=c['top_n'], max_lines=0)
        elif kind == 'status':
            model = 'akshab.stock.status.wizard'
            vals = dict(base_vals, date_from=c['date_from'], stagnant_days=c['stagnant_days'],
                        slow_cover_days=c['slow_cover_days'], reorder_cover_days=c['reorder_cover_days'], max_lines=0)
        elif kind == 'full':
            model = 'akshab.stock.report.wizard'
            vals = dict(base_vals, sales_days=period_days, stagnant_days=c['stagnant_days'],
                        slow_cover_days=c['slow_cover_days'], reorder_cover_days=c['reorder_cover_days'],
                        liquidation_discount=c['liquidation_discount'],
                        bucket_1=five[0], bucket_2=five[1], bucket_3=five[2], bucket_4=five[3], bucket_5=five[4])
        else:
            raise UserError(_('نوع التقرير غير معروف.'))
        wizard = self.env[model].create(vals)
        if fmt == 'xlsx':
            return wizard.action_export_xlsx()
        if fmt == 'form':
            return {
                'type': 'ir.actions.act_window',
                'name': wizard._report_basename,
                'res_model': model,
                'res_id': wizard.id,
                'view_mode': 'form',
                'views': [[False, 'form']],
                'target': 'new',
                'context': dict(self.env.context),
            }
        return wizard.action_print_pdf()
