# -*- coding: utf-8 -*-
"""Excel export of the inventory TURNOVER report.

Sheets: الملخص (KPIs, the equation, by category) · الأصناف (every product grouped by category)
· الأكثر دوراناً · الأقل دوراناً · بلا دوران · المنهجية.
"""
from .xlsx_mirror import MirrorXlsx, col


class StockTurnoverXlsx(MirrorXlsx):

    title_ar = 'تقرير معدل دوران المخزون'
    title_en = 'INVENTORY TURNOVER REPORT'

    # ------------------------------------------------------------------
    def _turn_specs(self, with_avg_daily=True, with_last_sale=True):
        cur = self.cur
        out = [col('متوسط المخزون (%s)' % cur, 'c', 'الدوران'), col('مبيعات الفترة', 'c', 'الدوران'),
               col('تكلفة المبيعات (%s)' % cur, 'c', 'الدوران'), col('دوران الفترة', 'c', 'الدوران'),
               col('دوران سنوي', 'c', 'الدوران'), col('أيام المخزون', 'c', 'الدوران')]
        if with_avg_daily:
            out.append(col('متوسط البيع اليومي', 'c', 'التغطية'))
        out.append(col('التغطية (يوم)', 'c', 'التغطية'))
        if with_last_sale:
            out.append(col('آخر بيع', 'c', 'التغطية'))
        return out

    def _turn_cells(self, r, with_avg_daily=True, with_last_sale=True, annual_kind='decb'):
        cells = [(r['avg_inventory'], 'money'), (r['sales_qty'], 'qty'), (r['cogs'], 'moneyb'), (r['turnover'], 'dec'),
                 (r['turnover_annual'], annual_kind), (r['dsi'], 'int')]
        if with_avg_daily:
            cells.append((r['avg_daily_cov'], 'dec'))
        cells.append((r['coverage'], 'int'))
        if with_last_sale:
            cells.append((r.get('last_sale_str'), 'c'))
        return cells

    def _turn_totals(self, o, with_avg_daily=True, with_last_sale=True):
        out = [(o['avg_inventory'], 'money'), (o['sales_qty'], 'qty'), (o['cogs'], 'money'), (o['turnover'], 'dec'),
               (o['turnover_annual'], 'dec'), (o['dsi'], 'int')]
        if with_avg_daily:
            out.append((o['avg_daily_cov'], 'dec'))
        out.append((o['coverage'], 'int'))
        if with_last_sale:
            out.append(('', 'blank'))
        return out

    # ------------------------------------------------------------------
    def build_report(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        tl = d['turnover_lists']
        opening = [col('الكمية', 'c', 'مخزون البداية'), col('القيمة (%s)' % cur, 'c', 'مخزون البداية')]

        # ============================== الملخص ==============================
        self.sheet('الملخص', desc='المؤشرات والفترة · معادلة الدوران · معدل الدوران حسب الفئة')
        self.header()
        self.kpis([
            (k['opening_value'], 'مخزون البداية (%s)' % cur, 'money', ''),
            (k['total_value'], 'مخزون النهاية (%s)' % cur, 'money', ''),
            (k['avg_inventory'], 'متوسط المخزون (%s)' % cur, 'money', ''),
            (k['cogs_window'], 'تكلفة المبيعات COGS (%s)' % cur, 'money', ''),
            (k['turnover_annual'], 'معدل الدوران (مرة/سنة)', 'dec', 'للفترة %.2f' % (k['turnover_period'] or 0.0)),
            (k['dsi'], 'أيام المخزون (Inventory Days)', 'int', ''),
        ])
        self.info([
            ('الفترة', self.period_text(m['date_from_date'], m['date_to_date'], m['period_days']),
             'نوع الأرصدة', m['mode_label']),
            ('المستودعات', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else ''),
             'أساس تكلفة المبيعات', m['cogs_basis_label']),
            ('متوسط البيع اليومي', 'على آخر %s يوم (من %s) — وعليه تُبنى التغطية' % (m['coverage_days'], m['coverage_from'])),
        ])

        # 1. equation
        self.section('المعادلة', 'أطراف المعادلة على مستوى نطاق التقرير كاملاً', cols=8)
        self.info([
            ('متوسط المخزون', '(مخزون البداية %s + مخزون النهاية %s) ÷ 2 = %s %s' % (
                '{:,.2f}'.format(k['opening_value']), '{:,.2f}'.format(k['total_value']),
                '{:,.2f}'.format(k['avg_inventory']), cur)),
            ('معدل الدوران للفترة', 'تكلفة المبيعات %s ÷ متوسط المخزون %s = %.2f مرة خلال %s يوم' % (
                '{:,.2f}'.format(k['cogs_window']), '{:,.2f}'.format(k['avg_inventory']),
                k['turnover_period'] or 0.0, m['period_days'])),
            ('معدل الدوران السنوي', '%.2f × (365 ÷ %s) = %.2f مرة/سنة' % (
                k['turnover_period'] or 0.0, m['period_days'], k['turnover_annual'] or 0.0)),
            ('أيام المخزون', '%s يوم ÷ %.2f = %s يوم (المدة اللازمة لبيع متوسط المخزون بمعدل تكلفة المبيعات)' % (
                m['period_days'], k['turnover_period'] or 0.0, '{:,.0f}'.format(k['dsi'] or 0.0))),
        ])

        # 2. by category
        self.section('معدل الدوران حسب الفئة', 'كل فئة مجمّعة من أصنافها', cols=14)
        specs = [col('الفئة', 'txt'), col('الأصناف')] + opening + \
            [col('الكمية', 'c', 'مخزون النهاية'), col('القيمة (%s)' % cur, 'c', 'مخزون النهاية')] + \
            self._turn_specs(with_last_sale=False)
        self.head(specs, freeze=False)
        cats = [c for c in d['categories'] if c['count_all'] > 0]
        for i, c in enumerate(cats):
            self.row([(c['name'], 'txtb'), (c['count_all'], 'int'), (c['opening_qty'], 'qty'), (c['opening_value'], 'money'),
                      (c['qty'], 'qtyb'), (c['value'], 'moneyb')] + self._turn_cells(c, with_last_sale=False), i % 2 == 1)
        self.total([('الإجمالي', 'txt'), (k['product_count_all'], 'int'), (k['opening_qty'], 'qty'), (k['opening_value'], 'money'),
                    (k['total_qty'], 'qty'), (k['total_value'], 'money'), (k['avg_inventory'], 'money'), (k['sales_qty'], 'qty'),
                    (k['cogs_window'], 'money'), (k['turnover_period'], 'dec'), (k['turnover_annual'], 'dec'), (k['dsi'], 'int'),
                    (k['avg_daily_cov'], 'dec'), (k['coverage'], 'int')])
        self.end_table()

        # ============================== الأصناف ==============================
        self.sheet('الأصناف', desc='معدل الدوران وأيام المخزون والتغطية لكل صنف — مجمّعة حسب فئة المنتج')
        self.header('معدل الدوران حسب الصنف — مجمّعة حسب الفئة بترتيب ثابت · الفترة %s' % self.period_text(
            m['date_from_date'], m['date_to_date'], m['period_days']))
        ps = self.product_specs()
        specs = ps[:-6] + opening + ps[-6:] + self._turn_specs()
        lc = self.product_label_cols()
        self.head(specs, autofilter=True)
        for c in cats:
            rows = [rw for rw in c['rows'] if rw['qty'] > 0 or rw['sales_qty'] > 0 or rw['opening_qty'] > 0]
            if not rows:
                continue
            rows.sort(key=lambda x: (-(x['turnover_annual'] or 0.0), -x['value']))
            cat = [('', 'blank')] * (lc - 1) + [(c['opening_qty'], 'qty'), (c['opening_value'], 'money'),
                                                (c['qty'], 'qty'), ('', 'blank'), ('', 'blank'), (c['value'], 'money'),
                                                ('', 'blank'), (c['sale_value'], 'money')] + \
                self._turn_totals(c)
            self.cat_row('%s — %s صنف' % (c['name'], '{:,.0f}'.format(c['count_all'])), cat)
            for i, rw in enumerate(rows):
                pc = self.product_cells(rw)
                self.row(pc[:-6] + [(rw['opening_qty'], 'qty'), (rw['opening_value'], 'money')] + pc[-6:] +
                         self._turn_cells(rw), i % 2 == 1)
        self.total([('الإجمالي العام', 'txt'), (k['opening_qty'], 'qty'), (k['opening_value'], 'money')] +
                   self.product_totals(k['total_qty'], k['total_value'], k['total_sale_value'])[lc - 1:] +
                   self._turn_totals(self._kpi_obj()), label_cols=lc)
        self.end_table()

        # ============================== ranked lists ==============================
        for key, sheet, title in (('top', 'الأكثر دوراناً', 'أعلى %s أصناف حسب معدل الدوران السنوي' % tl['top_n']),
                                  ('bottom', 'الأقل دوراناً', 'أدنى %s أصناف لها مخزون حالي ومبيعات خلال الفترة' % tl['top_n'])):
            if not tl[key]:
                continue
            self.sheet(sheet, desc=title)
            self.header(title)
            self.head(self.product_specs(with_category=True) + self._turn_specs(with_avg_daily=False), autofilter=True)
            for i, rw in enumerate(tl[key]):
                self.row(self.product_cells(rw, with_category=True) +
                         self._turn_cells(rw, with_avg_daily=False, annual_kind='decb' if key == 'top' else 'decr'), i % 2 == 1)
            self.end_table()

        # ============================== بلا دوران ==============================
        if tl['none_all']:
            self.sheet('بلا دوران', desc='أصناف لها مخزون ولم تُبع خلال الفترة — القائمة الكاملة')
            self.header('أصناف لها مخزون ولم تُبع خلال الفترة — %s بقيمة %s %s (%.1f%% من مخزون النهاية)' % (
                tl['none_items'], '{:,.2f}'.format(tl['none_value']), cur, tl['none_pct']))
            ps = self.product_specs(with_category=True)
            specs = ps[:-6] + opening + ps[-6:] + [
                col('آخر بيع', 'c', 'آخر حركة'), col('أيام بلا بيع', 'c', 'آخر حركة'),
                col('آخر استلام', 'c', 'آخر حركة'), col('أقدم كمية (يوم)', 'c', 'آخر حركة')]
            lc2 = self.product_label_cols(with_category=True)
            self.head(specs, autofilter=True)
            for i, rw in enumerate(tl['none_all']):
                pc = self.product_cells(rw, with_category=True)
                self.row(pc[:-6] + [(rw['opening_qty'], 'qty'), (rw['opening_value'], 'money')] + pc[-6:] +
                         [(rw['last_sale_str'], 'c'), (rw['days_since_sale'], 'int'), (rw['last_receipt_str'], 'c'),
                          (rw['max_age'], 'int')], i % 2 == 1)
            self.total([('الإجمالي — %s' % tl['none_items'], 'txt'), ('', 'blank'), ('', 'blank')] +
                       self.product_totals(tl['none_qty'], tl['none_value'], tl['none_sale_value'], with_category=True)[lc2 - 1:],
                       label_cols=lc2)
            self.end_table()

        # ============================== المنهجية ==============================
        self.method([
            ('الفترة', 'من %s إلى %s ‏(%s يوم)‏. مخزون البداية = الرصيد في بداية الفترة (معاد بناؤه من الحركات المنجزة بتكلفته حينها)، ومخزون النهاية = الرصيد بتاريخ المخزون.' % (m['date_from_date'], m['date_to_date'], m['period_days'])),
            ('تكلفة المبيعات COGS', '%s — صافي التسليمات للعملاء خلال الفترة (تشمل نقاط البيع وأوامر البيع؛ المرتجعات تُخصم على تاريخ البيع الأصلي).' % m['cogs_basis_label']),
            ('متوسط المخزون', '(مخزون البداية + مخزون النهاية) ÷ 2 بالقيمة، على مستوى كل صنف ثم تُجمع للفئة والإجمالي.'),
            ('معدل الدوران', 'معدل الفترة = COGS ÷ متوسط المخزون. المعدل السنوي = معدل الفترة × (365 ÷ عدد أيام الفترة).'),
            ('أيام المخزون', 'Inventory Days = عدد أيام الفترة ÷ معدل الدوران للفترة = المدة اللازمة لبيع متوسط المخزون بمعدل تكلفة المبيعات.'),
            ('التغطية', 'الكمية الحالية ÷ متوسط البيع اليومي المحسوب على آخر %s يوم (من %s) = كم يوماً يكفي المخزون الحالي بمعدل البيع الأخير.' % (m['coverage_days'], m['coverage_from'])),
            ('القوائم', 'الأكثر دوراناً: أعلى %s أصناف حسب المعدل السنوي · الأقل دوراناً: أدنى %s أصناف لها مخزون حالي ومبيعات خلال الفترة · بلا دوران: أصناف لها مخزون ولم تُبع خلال الفترة (مرتبة حسب القيمة).' % (tl['top_n'], tl['top_n'])),
        ] + self.method_common())

    def _kpi_obj(self):
        k = self.k
        return {'avg_inventory': k['avg_inventory'], 'sales_qty': k['sales_qty'], 'cogs': k['cogs_window'],
                'turnover': k['turnover_period'], 'turnover_annual': k['turnover_annual'], 'dsi': k['dsi'],
                'avg_daily_cov': k['avg_daily_cov'], 'coverage': k['coverage']}
