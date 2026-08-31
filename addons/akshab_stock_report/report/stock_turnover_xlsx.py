# -*- coding: utf-8 -*-
"""Excel export of the Akshab inventory TURNOVER report (by category, then by product)."""
from .xlsx_base import AkshabXlsxBase
from .stock_report_engine import ar_items


class StockTurnoverXlsx(AkshabXlsxBase):

    subtitle = 'INVENTORY TURNOVER REPORT'

    def build_sheets(self):
        self._sheet_summary()
        self._sheet_categories()
        self._sheet_products()
        self._sheet_lists()
        self._sheet_method()

    # ------------------------------------------------------------------
    def _meta_rows(self):
        m = self.m
        return [
            ('الفترة', 'من %s إلى %s \u200f(%s يوم)\u200f' % (m['date_from_date'], m['date_to_date'], m['period_days']),
             'نوع الأرصدة', m['mode_label']),
            ('المستودعات', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else ''),
             'متوسط البيع اليومي', 'على آخر %s يوم (من %s) — وعليه تُبنى التغطية' % (m['coverage_days'], m['coverage_from'])),
        ]

    def _headers(self, first_cols, product=False):
        cur = self.cur
        end = ([('مخزون النهاية (كمية)', 'c'), ('الوحدة', 'c'), ('تكلفة الوحدة (%s)' % cur, 'c'), ('مخزون النهاية بالتكلفة (%s)' % cur, 'c'),
                ('سعر البيع (%s)' % cur, 'c'), ('القيمة البيعية (%s)' % cur, 'c')] if product
               else [('مخزون النهاية (كمية)', 'c'), ('مخزون النهاية (%s)' % cur, 'c')])
        return first_cols + [
            ('مخزون البداية (كمية)', 'c'), ('مخزون البداية (%s)' % cur, 'c')] + end + [
            ('متوسط المخزون (%s)' % cur, 'c'), ('مبيعات الفترة (كمية)', 'c'), ('تكلفة المبيعات COGS (%s)' % cur, 'c'),
            ('معدل الدوران للفترة', 'c'), ('معدل الدوران السنوي', 'c'), ('أيام المخزون', 'c'),
            ('متوسط البيع اليومي', 'c'), ('التغطية (يوم)', 'c')]

    def _values(self, obj, product=False):
        end = (self._std_values(obj) if product else [(obj['qty'], 'qty'), (obj['value'], 'money')])
        return [(obj['opening_qty'], 'qty'), (obj['opening_value'], 'money')] + end + [
                (obj['avg_inventory'], 'money'), (obj['sales_qty'], 'qty'), (obj['cogs'], 'moneyb'),
                (obj['turnover'], 'dec'), (obj['turnover_annual'], 'dec'), (obj['dsi'], 'int'),
                (obj['avg_daily_cov'], 'dec'), (obj['coverage'], 'int')]

    def _totals(self, label, obj, blanks_before=0, blanks_after=0, product=False):
        end = (self._std_totals(obj['qty'], obj['value'], obj['sale_value']) if product
               else [(obj['qty'], 'qty'), (obj['value'], 'money')])
        return [(label, 'txt')] + [('', 'blank')] * blanks_before + [
            (obj['opening_qty'], 'qty'), (obj['opening_value'], 'money')] + end + [
            (obj['avg_inventory'], 'money'), (obj['sales_qty'], 'qty'), (obj['cogs'], 'money'),
            (obj['turnover'] or 0.0, 'money'), (obj['turnover_annual'] or 0.0, 'money'), (obj['dsi'] or 0.0, 'int'),
            (obj['avg_daily_cov'], 'money'), (obj['coverage'] or 0.0, 'int')] + [('', 'blank')] * blanks_after

    def _kpi_as_obj(self):
        k = self.k
        return {'opening_qty': k['opening_qty'], 'opening_value': k['opening_value'], 'qty': k['total_qty'], 'value': k['total_value'],
                'sale_value': k['total_sale_value'],
                'avg_inventory': k['avg_inventory'], 'sales_qty': k['sales_qty'], 'cogs': k['cogs_window'],
                'turnover': k['turnover_period'], 'turnover_annual': k['turnover_annual'], 'dsi': k['dsi'],
                'avg_daily_cov': k['avg_daily_cov'], 'coverage': k['coverage']}

    # ------------------------------------------------------------------
    def _sheet_summary(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        tl = d['turnover_lists']
        ws = self._new_sheet('الملخص', [30] + [16] * 18)
        r = self._title_block(ws, 'تقرير معدل دوران المخزون', self._meta_rows(), span=8)
        r = self._kpi_row(ws, r, [
            (k['opening_value'], 'مخزون البداية (%s)' % cur, 'money'),
            (k['total_value'], 'مخزون النهاية (%s)' % cur, 'money'),
            (k['avg_inventory'], 'متوسط المخزون (%s)' % cur, 'money'),
            (k['cogs_window'], 'تكلفة المبيعات COGS (%s)' % cur, 'money'),
            (k['turnover_period'], 'معدل الدوران للفترة (%s يوم)' % m['period_days'], 'dec'),
            (k['turnover_annual'], 'معدل الدوران السنوي', 'dec'),
            (k['dsi'], 'أيام المخزون (Inventory Days)', 'int'),
        ])
        r = self._section(ws, r, '١', 'المعادلة', 'كيف حُسبت الأرقام أعلاه', span=6)
        eq = [
            ('متوسط المخزون', '(مخزون البداية %s + مخزون النهاية %s) ÷ 2 = %s' % ('{:,.2f}'.format(k['opening_value']), '{:,.2f}'.format(k['total_value']), '{:,.2f}'.format(k['avg_inventory']))),
            ('معدل الدوران للفترة', 'COGS %s ÷ متوسط المخزون %s = %s' % ('{:,.2f}'.format(k['cogs_window']), '{:,.2f}'.format(k['avg_inventory']), '{:,.2f}'.format(k['turnover_period'] or 0.0))),
            ('معدل الدوران السنوي', 'معدل الفترة × (365 ÷ %s يوم) = %s' % (m['period_days'], '{:,.2f}'.format(k['turnover_annual'] or 0.0))),
            ('أيام المخزون', '%s يوم ÷ معدل الدوران للفترة = %s يوم' % (m['period_days'], '{:,.0f}'.format(k['dsi'] or 0.0))),
        ]
        for a, b in eq:
            ws.write(r, 0, a, self.f_meta_lbl)
            ws.merge_range(r, 1, r, 8, b, self.f_meta_val)
            r += 1
        r += 1
        # the three lists (top N) — full lists on their own sheet
        lists = [('٢', 'الأصناف الأكثر دوراناً', 'أعلى %s أصناف حسب معدل الدوران السنوي' % tl['top_n'], tl['top']),
                 ('٣', 'الأصناف الأقل دوراناً', 'أدنى %s أصناف لها مخزون حالي ومبيعات خلال الفترة' % tl['top_n'], tl['bottom']),
                 ('٤', 'أصناف بلا دوران', 'لها مخزون ولم تُبع خلال الفترة — %s بقيمة %s %s · القائمة الكاملة في ورقة "بلا دوران"' % (
                     tl['none_items'], '{:,.2f}'.format(tl['none_value']), cur), tl['none'])]
        for idx, title, hint, subset in lists:
            if not subset:
                continue
            r = self._section(ws, r, idx, title, hint, span=10)
            r = self._write_header(ws, r, [('الصنف', 'txt'), ('الفئة', 'txt')] + self._std_headers() +
                                          [('متوسط المخزون', 'c'), ('مبيعات الفترة', 'c'), ('COGS', 'c'),
                                           ('معدل الدوران السنوي', 'c'), ('أيام المخزون', 'c'), ('التغطية (يوم)', 'c'), ('آخر بيع', 'c')])
            for i, rw in enumerate(subset):
                self._write_row(ws, r, [(rw['display_name'], 'txtb'), (rw['category'], 'txt')] + self._std_values(rw) +
                                       [(rw['avg_inventory'], 'money'), (rw['sales_qty'], 'qty'), (rw['cogs'], 'money'),
                                        (rw['turnover_annual'], 'dec'), (rw['dsi'], 'int'), (rw['coverage'], 'int'), (rw['last_sale_str'], 'c')], i % 2 == 1)
                r += 1
            r += 1
        ws.freeze_panes(3, 0)

    # ------------------------------------------------------------------
    def _sheet_categories(self):
        d, m = self.d, self.m
        headers = self._headers([('الفئة', 'txt'), ('عدد الأصناف', 'c')])
        ws = self._new_sheet('حسب الفئة', [30, 12] + [15] * (len(headers) - 2))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'معدل دوران المخزون حسب الفئة', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'الفترة من %s إلى %s · كل فئة مجمّعة من أصنافها' % (m['date_from_date'], m['date_to_date']), self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        cats = [c for c in d['categories'] if c['count_all'] > 0]
        for i, c in enumerate(cats):
            self._write_row(ws, r, [(c['name'], 'txtb'), (c['count_all'], 'int')] + self._values(c), i % 2 == 1)
            r += 1
        tot = self._totals('الإجمالي', self._kpi_as_obj())
        tot.insert(1, (self.k['product_count_all'], 'int'))
        self._write_total(ws, r, tot)
        if cats:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_products(self):
        d, m = self.d, self.m
        headers = self._headers([('الصنف', 'txt'), ('الفئة', 'txt')], product=True) + [('آخر بيع', 'c'), ('آخر استلام', 'c')]
        ws = self._new_sheet('الأصناف', [44, 22] + [14] * (len(headers) - 2))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'معدل دوران المخزون حسب الصنف', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'مجمّعة حسب الفئة مع إجمالي لكل فئة · الفترة من %s إلى %s' % (m['date_from_date'], m['date_to_date']), self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        for c in d['categories']:
            rows = [rw for rw in c['rows'] if rw['qty'] > 0 or rw['sales_qty'] > 0 or rw['opening_qty'] > 0]
            if not rows:
                continue
            ws.merge_range(r, 0, r, len(headers) - 1, '%s — %s · دوران سنوي %s · أيام المخزون %s' % (
                c['name'], ar_items(len(rows)), '{:.2f}'.format(c['turnover_annual'] or 0.0), '{:,.0f}'.format(c['dsi'] or 0.0)), self.f_sub)
            r += 1
            rows.sort(key=lambda x: (-(x['turnover_annual'] or 0.0), -x['value']))
            for i, rw in enumerate(rows):
                self._write_row(ws, r, [(rw['display_name'], 'txtb'), (rw['category'], 'txt')] + self._values(rw, product=True) +
                                [(rw['last_sale_str'], 'c'), (rw['last_receipt_str'], 'c')], i % 2 == 1)
                r += 1
            self._write_total(ws, r, self._totals('إجمالي %s' % c['name'], c, blanks_before=1, blanks_after=2, product=True))
            r += 1
        self._write_total(ws, r, self._totals('الإجمالي العام', self._kpi_as_obj(), blanks_before=1, blanks_after=2, product=True))
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_lists(self):
        """Full lists: every product without turnover, and all products ranked by annual turnover."""
        d, m, cur = self.d, self.m, self.cur
        tl = d['turnover_lists']
        headers = [('الصنف', 'txt'), ('الفئة', 'txt'), ('مخزون البداية (كمية)', 'c')] + self._std_headers() + \
                  [('آخر بيع', 'c'), ('أيام بلا بيع', 'c'), ('آخر استلام', 'c'), ('أقدم كمية (يوم)', 'c')]
        ws = self._new_sheet('بلا دوران', [44, 22] + [14] * (len(headers) - 2))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'أصناف بلا دوران — لها مخزون ولم تُبع خلال الفترة', self.f_title)
        ws.merge_range(1, 0, 1, 8, '%s بقيمة %s %s (%s من مخزون النهاية) · الفترة من %s إلى %s' % (
            tl['none_items'], '{:,.2f}'.format(tl['none_value']), cur, '{:.1f}%'.format(tl['none_pct']),
            m['date_from_date'], m['date_to_date']), self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        for i, rw in enumerate(tl['none_all']):
            self._write_row(ws, r, [(rw['display_name'], 'txtb'), (rw['category'], 'txt'), (rw['opening_qty'], 'qty')] + self._std_values(rw) +
                                   [(rw['last_sale_str'], 'c'), (rw['days_since_sale'], 'int'), (rw['last_receipt_str'], 'c'),
                                    (rw['max_age'], 'int')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي — %s' % tl['none_items'], 'txt'), ('', 'blank'), ('', 'blank')] +
                                 self._std_totals(tl['none_qty'], tl['none_value'], tl['none_sale_value']) + [('', 'blank')] * 4)
        if tl['none_all']:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_method(self):
        m = self.m
        tl = self.d['turnover_lists']
        self._method_sheet([
            ('الفترة', 'من %s إلى %s \u200f(%s يوم)\u200f. مخزون البداية = الرصيد في بداية الفترة (معاد بناؤه من الحركات المنجزة)، ومخزون النهاية = الرصيد بتاريخ المخزون.' % (m['date_from_date'], m['date_to_date'], m['period_days'])),
            ('التقييم', '%s × الكمية (مخزون البداية بتكلفته في تاريخ البداية).' % m['cost_basis_label']),
            ('تكلفة المبيعات COGS', '%s. صافي التسليمات للعملاء خلال الفترة (المرتجعات تُخصم على تاريخ البيع الأصلي).' % m['cogs_basis_label']),
            ('متوسط المخزون', '(مخزون البداية + مخزون النهاية) ÷ 2 بالقيمة.'),
            ('معدل الدوران', 'معدل الفترة = COGS ÷ متوسط المخزون. المعدل السنوي = معدل الفترة × (365 ÷ عدد أيام الفترة).'),
            ('أيام المخزون (Inventory Days)', 'عدد أيام الفترة ÷ معدل الدوران للفترة = المدة التي يستغرقها بيع متوسط المخزون بمعدل تكلفة المبيعات.'),
            ('التغطية', 'في جداول الفئات والأصناف: الكمية الحالية ÷ متوسط البيع اليومي المحسوب على آخر %s يوم (من %s) = كم يوماً يكفي المخزون الحالي بمعدل البيع الأخير.' % (m['coverage_days'], m['coverage_from'])),
            ('القوائم', 'الأكثر دوراناً: أعلى %s أصناف حسب المعدل السنوي · الأقل دوراناً: أدنى %s أصناف لها مخزون حالي ومبيعات خلال الفترة · بلا دوران: أصناف لها مخزون ولم تُبع خلال الفترة (مرتبة حسب القيمة).' % (tl['top_n'], tl['top_n'])),
            ('الكميات', 'المبيعات المسجلة دون رصيد كافٍ تُعد صفراً في مخزون البداية والنهاية ولا تدخل في القيمة، بينما تبقى المبيعات نفسها ضمن تكلفة المبيعات.'),
        ])
