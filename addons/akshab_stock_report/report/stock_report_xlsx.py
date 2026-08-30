# -*- coding: utf-8 -*-
"""Excel export of the Akshab comprehensive inventory status report."""
from .xlsx_base import AkshabXlsxBase


class StockReportXlsx(AkshabXlsxBase):

    subtitle = 'INVENTORY STATUS REPORT'

    def build_sheets(self):
        self._sheet_summary()
        self._sheet_products('الأصناف الراكدة', self.d['stagnant'], 'stagnant')
        self._sheet_products('بطيئة الحركة', self.d['slow'], 'slow')
        if self.d['transfers']:
            self._sheet_transfers()
        self._sheet_products('الأصناف النشطة', self.d['active'], 'active')
        if self.d['new']:
            self._sheet_products('أصناف جديدة', self.d['new'], 'new')
        if self.d['out']:
            self._sheet_products('نافدة لها طلب', self.d['out'], 'out')
        self._sheet_all_products()
        self._sheet_method()

    def _meta_rows(self):
        m = self.m
        return [
            ('تاريخ المخزون', m['date_to_display'], 'نوع الأرصدة', m['mode_label']),
            ('الفروع', m['warehouses_display'], 'الفئات', m['categories_display']),
            ('فترة تحليل المبيعات', 'من %s إلى %s (%s يوم)' % (m['sales_from'], m['sales_to'], m['sales_days']),
             'معيار الركود', 'لم يُبع خلال آخر %s يوم · بطيء الحركة: تغطية > %s يوم' % (m['stagnant_days'], m['slow_cover_days'])),
            ('تاريخ الطباعة', m['print_date'], 'العملة / التقييم', '%s · %s' % (m['currency_name'], m['cost_basis_label'])),
        ]

    def _sheet_summary(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        ws = self._new_sheet('الملخص', [26, 16, 16, 16, 18, 16, 16, 16, 16, 16, 16, 16, 16, 14])
        r = self._title_block(ws, 'تقرير المخزون', self._meta_rows(), span=8)

        # KPI tiles (2 rows: values then labels)
        kpis = [
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money'),
            (k['product_count'], 'عدد الأصناف بالمخزون', 'int'),
            (k['total_qty'], 'إجمالي الكميات', 'int'),
            (k['active_value'], 'مخزون نشط (%s) — %.1f%%' % (cur, k['active_pct']), 'money'),
            (k['slow_value'], 'بطيء الحركة / فائض (%s) — %.1f%%' % (cur, k['slow_pct']), 'money'),
            (k['stagnant_value'], 'مخزون راكد (%s) — %.1f%% — %d صنف' % (cur, k['stagnant_pct'], k['stagnant_count']), 'money_red'),
            (k['avg_age'], 'متوسط عمر المخزون (يوم)', 'int'),
            (k['expected_cash'], 'سيولة متوقعة من التصفية (%s)' % cur, 'money'),
            (k['health_score'], 'مؤشر صحة المخزون / 100 — %s' % k['health_label'], 'int'),
            (k['turnover'], 'معدل دوران المخزون (مرة/سنة) — أيام المخزون %s' % (round(k['dsi']) if k['dsi'] else '-'), 'dec'),
        ]
        r = self._kpi_row(ws, r, kpis)

        # 1. status summary
        r = self._section(ws, r, '١', 'ملخص حالة المخزون', 'تصنيف كل صنف حسب حركة بيعه خلال فترة التحليل', span=6)
        r = self._write_header(ws, r, [('الحالة', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'),
                                       ('القيمة بالتكلفة (%s)' % cur, 'c'), ('النسبة من القيمة', 'c'),
                                       ('القيمة بسعر البيع (%s)' % cur, 'c'), ('التعريف', 'txt')])
        defs = {
            'active': 'يُباع خلال فترة التحليل وكميته مناسبة لمعدل بيعه',
            'slow': 'يُباع لكن كميته تكفي لأكثر من %s يوماً (فائض مخزون)' % m['slow_cover_days'],
            'stagnant': 'لم يُسجل له أي بيع خلال آخر %s يوماً' % m['stagnant_days'],
            'new': 'استُلم خلال آخر %s يوماً ولم يُبع بعد' % m['new_days'],
        }
        for i, s in enumerate(d['status_summary']):
            self._write_row(ws, r, [(s['label'], 'badge:%s' % s['key']), (s['count'], 'int'), (s['qty'], 'qty'),
                                    (s['value'], 'money'), (s['pct'], 'pct'), (s['sale_value'], 'money'),
                                    (defs[s['key']], 'txt')], i % 2 == 1)
            r += 1
        st = d['status_total']
        self._write_total(ws, r, [('الإجمالي', 'txt'), (st['count'], 'int'), (st['qty'], 'qty'), (st['value'], 'money'),
                                  (100.0, 'pct'), (st['sale_value'], 'money'), ('', 'blank')])
        r += 2

        # 2. aging
        r = self._section(ws, r, '٢', 'أعمار المخزون', 'عمر الكمية منذ استلامها في الفرع (أساس FIFO)', span=6)
        r = self._write_header(ws, r, [('الفئة العمرية', 'txt'), ('الكمية', 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'), ('النسبة', 'c')])
        for i, b in enumerate(d['aging']['buckets']):
            self._write_row(ws, r, [(b['label'], 'txtb'), (b['qty'], 'qty'), (b['value'], 'money'), (b['pct'], 'pct')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي — متوسط العمر %d يوم' % round(d['aging']['avg_age']), 'txt'),
                                  (d['aging']['total_qty'], 'qty'), (d['aging']['total_value'], 'money'), (100.0, 'pct')])
        r += 1
        ws.write(r, 0, 'المخزون الأقدم من %s يوم يمثل %.1f%% من القيمة (%s %s)، ومنه %.1f%% أقدم من سنة.' % (
            m['buckets'][3], k['old_pct'], '{:,.2f}'.format(k['old_value']), cur, k['over_year_pct']), self.f_note)
        r += 2

        # aging matrices
        for key, title in (('aging_by_warehouse', 'أعمار المخزون حسب الفرع (القيمة بالتكلفة)'),
                           ('aging_by_category', 'أعمار المخزون حسب الفئة (القيمة بالتكلفة)')):
            mat = d[key]
            if not mat['rows'] or (key == 'aging_by_warehouse' and not m['multi_warehouse']):
                continue
            ws.merge_range(r, 0, r, 8, title, self.f_sub)
            r += 1
            r = self._write_header(ws, r, [('الفئة' if 'category' in key else 'الفرع', 'txt')] +
                                   [(lbl, 'c') for lbl in mat['columns']] +
                                   [('الإجمالي', 'c'), ('نسبة الأقدم من %s يوم' % m['buckets'][3], 'c')])
            for i, ag in enumerate(mat['rows']):
                self._write_row(ws, r, [(ag['name'], 'txtb')] + [(v, 'money') for v in ag['values']] +
                                [(ag['total'], 'moneyb'), (ag['pct_old'], 'pct')], i % 2 == 1)
                r += 1
            self._write_total(ws, r, [('الإجمالي', 'txt')] + [(v, 'money') for v in mat['totals']] +
                              [(mat['total'], 'money'), (k['old_pct'], 'pct')])
            r += 2

        # 3. by warehouse
        r = self._section(ws, r, '٣', 'المخزون حسب الفرع', None, span=11)
        r = self._write_header(ws, r, [('الفرع', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'), ('القيمة (%s)' % cur, 'c'),
                                       ('النسبة', 'c'), ('نشط (%s)' % cur, 'c'), ('بطيء الحركة (%s)' % cur, 'c'),
                                       ('راكد (%s)' % cur, 'c'), ('نسبة الراكد', 'c'), ('أصناف بلا بيع في الفرع', 'c'),
                                       ('مبيعات الفترة (كمية)', 'c'), ('متوسط العمر (يوم)', 'c'), ('دوران سنوي', 'c')])
        for i, bw in enumerate(d['by_warehouse']):
            self._write_row(ws, r, [(bw['name'], 'txtb'), (bw['count'], 'int'), (bw['qty'], 'qty'), (bw['value'], 'money'),
                                    (bw['pct'], 'pct'), (bw['active_value'], 'money'), (bw['slow_value'], 'money'),
                                    (bw['stagnant_value'], 'moneyr'), (bw['stagnant_pct'], 'pct'), (bw['idle_count'], 'int'),
                                    (bw['sales_qty'], 'qty'), (bw['avg_age'], 'int'), (bw['turnover'], 'dec')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'),
                                  (100.0, 'pct'), (k['active_value'], 'money'), (k['slow_value'], 'money'), (k['stagnant_value'], 'money'),
                                  (k['stagnant_pct'], 'pct'), ('', 'blank'), ('', 'blank'), (k['avg_age'], 'int'), (k['turnover'], 'money')])
        r += 2

        # 4. by category
        r = self._section(ws, r, '٤', 'المخزون حسب الفئة', 'مرتبة تنازلياً حسب القيمة', span=11)
        r = self._write_header(ws, r, [('الفئة', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'), ('القيمة (%s)' % cur, 'c'),
                                       ('النسبة', 'c'), ('نشط (%s)' % cur, 'c'), ('بطيء الحركة (%s)' % cur, 'c'),
                                       ('راكد (%s)' % cur, 'c'), ('نسبة الراكد', 'c'), ('أصناف راكدة', 'c'),
                                       ('مبيعات الفترة (كمية)', 'c'), ('متوسط العمر (يوم)', 'c'), ('دوران سنوي', 'c')])
        for i, bc in enumerate(d['by_category']):
            self._write_row(ws, r, [(bc['name'], 'txtb'), (bc['count'], 'int'), (bc['qty'], 'qty'), (bc['value'], 'money'),
                                    (bc['pct'], 'pct'), (bc['active_value'], 'money'), (bc['slow_value'], 'money'),
                                    (bc['stagnant_value'], 'moneyr'), (bc['stagnant_pct'], 'pct'), (bc['stagnant_count'], 'int'),
                                    (bc['sales_qty'], 'qty'), (bc['avg_age'], 'int'), (bc['turnover'], 'dec')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'),
                                  (100.0, 'pct'), (k['active_value'], 'money'), (k['slow_value'], 'money'), (k['stagnant_value'], 'money'),
                                  (k['stagnant_pct'], 'pct'), (k['stagnant_count'], 'int'), ('', 'blank'), (k['avg_age'], 'int'), (k['turnover'], 'money')])
        r += 2

        # 5. plan
        r = self._section(ws, r, '٥', 'خلاصة التوصيات وخطة التصفية', 'السيولة المتوقعة = الكمية × سعر البيع × (1 − الخصم)؛ الخصم لكل صنف هو الأقل بين %s%% وهامش الربح' % m['liquidation_discount'], span=6)
        r = self._write_header(ws, r, [('الإجراء المقترح', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'), ('التكلفة (%s)' % cur, 'c'),
                                       ('القيمة بسعر البيع (%s)' % cur, 'c'), ('السيولة المتوقعة (%s)' % cur, 'c'), ('نسبة الاسترداد من التكلفة', 'c')])
        for i, pl in enumerate(d['plan']['rows']):
            self._write_row(ws, r, [(pl['label'], 'badge:%s' % pl['key']), (pl['count'], 'int'), (pl['qty'], 'qty'), (pl['cost'], 'money'),
                                    (pl['sale_value'], 'money'), (pl['expected_cash'], 'moneyg'), (pl['recovery_pct'], 'pct')], i % 2 == 1)
            r += 1
        pt = d['plan']['total']
        self._write_total(ws, r, [('الإجمالي', 'txt'), (pt['count'], 'int'), (pt['qty'], 'qty'), (pt['cost'], 'money'),
                                  (pt['sale_value'], 'money'), (pt['expected_cash'], 'money'), (pt['recovery_pct'], 'pct')])
        r += 2

        # insights
        ws.merge_range(r, 0, r, 8, 'أبرز النتائج', self.f_sub)
        r += 1
        for i, ins in enumerate(d['insights']):
            ws.set_row(r, 30)
            ws.merge_range(r, 0, r, 8, '%d. %s' % (i + 1, ins), self.f_insight)
            r += 1
        r += 1
        ws.merge_range(r, 0, r, 8, 'قرار الإدارة / ملاحظات', self.f_sub)
        r += 1
        for _ in range(4):
            ws.set_row(r, 22)
            ws.merge_range(r, 0, r, 8, '', self.f_insight)
            r += 1
        ws.freeze_panes(3, 0)

    # ------------------------------------------------------------------
    def _product_headers(self, kind):
        cur = self.cur
        wh_cols = [('%s' % wh['name'], 'c') for wh in self.m['warehouses']] if self.m['multi_warehouse'] else []
        base = [('الصنف', 'txt'), ('الرمز', 'txt'), ('الفئة', 'txt'), ('الحالة', 'c')]
        if kind == 'stagnant':
            cols = [('الكمية', 'c')] + wh_cols + [
                ('تكلفة الوحدة', 'c'), ('التكلفة الإجمالية (%s)' % cur, 'c'), ('سعر البيع بدون ضريبة', 'c'),
                ('القيمة بسعر البيع', 'c'), ('آخر بيع', 'c'), ('أيام بلا بيع', 'c'), ('آخر استلام', 'c'),
                ('متوسط العمر (يوم)', 'c'), ('أقدم كمية (يوم)', 'c'), ('هامش الربح', 'c'), ('أقصى خصم دون خسارة', 'c'),
                ('الخصم المطبق', 'c'), ('السيولة المتوقعة (%s)' % cur, 'c'), ('التوصية', 'c'), ('تفصيل التوصية', 'txt')]
        elif kind == 'slow':
            cols = [('الكمية', 'c')] + wh_cols + [
                ('التكلفة الإجمالية (%s)' % cur, 'c'), ('سعر البيع بدون ضريبة', 'c'), ('مبيعات الفترة', 'c'), ('متوسط البيع اليومي', 'c'),
                ('أيام التغطية', 'c'), ('الفائض (كمية)', 'c'), ('قيمة الفائض (%s)' % cur, 'c'), ('السيولة المتوقعة من الفائض', 'c'),
                ('آخر بيع', 'c'), ('متوسط العمر (يوم)', 'c'), ('التوصية', 'c'), ('تفصيل التوصية', 'txt')]
        elif kind == 'out':
            cols = [('مبيعات الفترة', 'c'), ('متوسط البيع اليومي', 'c'), ('آخر بيع', 'c'), ('آخر استلام', 'c'),
                    ('كمية قادمة', 'c'), ('سعر البيع بدون ضريبة', 'c'), ('تكلفة الوحدة', 'c'), ('التوصية', 'c'), ('تفصيل التوصية', 'txt')]
        else:  # active / new
            cols = [('الكمية', 'c')] + wh_cols + [
                ('التكلفة الإجمالية (%s)' % cur, 'c'), ('سعر البيع بدون ضريبة', 'c'), ('مبيعات الفترة', 'c'), ('متوسط البيع اليومي', 'c'),
                ('أيام التغطية', 'c'), ('آخر بيع', 'c'), ('آخر استلام', 'c'), ('كمية قادمة', 'c'), ('متوسط العمر (يوم)', 'c'),
                ('التوصية', 'c'), ('تفصيل التوصية', 'txt')]
        return base + cols

    def _product_values(self, r, kind):
        wh_vals = [(r['wh_qty'].get(wh['id'], 0.0), 'qty') for wh in self.m['warehouses']] if self.m['multi_warehouse'] else []
        base = [(r['name'], 'txtb'), (r['code'], 'txt'), (r['category'], 'txt'), (r['status_label'], 'badge:%s' % r['status'])]
        last_sale = r['last_sale_str']
        if kind == 'stagnant':
            cols = [(r['qty'], 'qty')] + wh_vals + [
                (r['unit_cost'], 'money'), (r['value'], 'moneyb'), (r['price'], 'money'), (r['sale_value'], 'money'),
                (last_sale, 'c'), (r['days_since_sale'], 'int'), (r['last_receipt_str'], 'c'),
                (r['avg_age'], 'int'), (r['max_age'], 'int'), (r['margin_pct'], 'pct'), (r['max_discount'], 'pct'),
                (r['applied_discount'], 'pct'), (r['expected_cash'], 'moneyg'), (r['action_label'], 'badge:%s' % r['action']),
                (r['action_text'], 'txt')]
        elif kind == 'slow':
            cols = [(r['qty'], 'qty')] + wh_vals + [
                (r['value'], 'money'), (r['price'], 'money'), (r['sales_qty'], 'qty'), (r['avg_daily'], 'dec'),
                (r['cover_days'], 'int'), (r['excess_qty'], 'qty'), (r['excess_value'], 'moneyb'), (r['expected_cash'], 'moneyg'),
                (last_sale, 'c'), (r['avg_age'], 'int'), (r['action_label'], 'badge:%s' % r['action']), (r['action_text'], 'txt')]
        elif kind == 'out':
            cols = [(r['sales_qty'], 'qty'), (r['avg_daily'], 'dec'), (last_sale, 'c'), (r['last_receipt_str'], 'c'),
                    (r['incoming_qty'], 'qty'), (r['price'], 'money'), (r['unit_cost'], 'money'),
                    (r['action_label'], 'badge:%s' % r['action']), (r['action_text'], 'txt')]
        else:
            cols = [(r['qty'], 'qty')] + wh_vals + [
                (r['value'], 'money'), (r['price'], 'money'), (r['sales_qty'], 'qty'), (r['avg_daily'], 'dec'),
                (r['cover_days'], 'int'), (last_sale, 'c'), (r['last_receipt_str'], 'c'), (r['incoming_qty'], 'qty'),
                (r['avg_age'], 'int'), (r['action_label'], 'badge:%s' % r['action']), (r['action_text'], 'txt')]
        return base + cols

    def _sheet_products(self, name, rows, kind):
        headers = self._product_headers(kind)
        widths = [38, 12, 22, 14] + [14] * (len(headers) - 4)
        widths[-1] = 44
        ws = self._new_sheet(name, widths)
        titles = {
            'stagnant': ('الأصناف الراكدة وتوصيات التصفية', 'لم تُبع خلال آخر %s يوماً — مرتبة تنازلياً حسب القيمة' % self.m['stagnant_days']),
            'slow': ('الأصناف بطيئة الحركة (فائض مخزون)', 'تُباع لكن كميتها تكفي لأكثر من %s يوماً — مرتبة حسب قيمة الفائض' % self.m['slow_cover_days']),
            'active': ('الأصناف النشطة', 'مرتبة تنازلياً حسب كمية المبيعات خلال فترة التحليل'),
            'new': ('الأصناف الجديدة', 'استُلمت خلال آخر %s يوماً ولم تُبع بعد' % self.m['new_days']),
            'out': ('أصناف نافدة لها طلب', 'بيعت خلال فترة التحليل ورصيدها الآن صفر — فرص بيع مفقودة'),
        }
        title, hint = titles[kind]
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, min(8, len(headers) - 1), title, self.f_title)
        ws.merge_range(1, 0, 1, min(8, len(headers) - 1), '%s · تاريخ المخزون %s · %s' % (hint, self.m['date_to_display'], self.m['company_name']), self.f_hint)
        r = 3
        r = self._write_header(ws, r, headers)
        ws.repeat_rows(r - 1)
        first = r
        all_vals = [self._product_values(row, kind) for row in rows]
        for i, vals in enumerate(all_vals):
            self._write_row(ws, r, vals, i % 2 == 1)
            r += 1
        if rows:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
            # totals
            tot = [('الإجمالي: %d صنف' % len(rows), 'txt'), ('', 'blank'), ('', 'blank'), ('', 'blank')]
            for i in range(4, len(headers)):
                k = all_vals[0][i][1]
                if k in ('qty', 'money', 'moneyb', 'moneyg', 'moneyr') and headers[i][0] not in ('تكلفة الوحدة', 'سعر البيع'):
                    total = sum(float(v[i][0] or 0.0) for v in all_vals)
                    tot.append((total, 'qty' if k == 'qty' else 'money'))
                else:
                    tot.append(('', 'blank'))
            self._write_total(ws, r, tot)
        else:
            ws.write(r, 0, 'لا توجد أصناف في هذه الفئة ضمن نطاق التقرير.', self.f_note)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    def _sheet_all_products(self):
        cur, m = self.cur, self.m
        wh_cols = [('كمية %s' % wh['name'], 'c') for wh in m['warehouses']] if m['multi_warehouse'] else []
        headers = [('الصنف', 'txt'), ('الرمز', 'txt'), ('الفئة', 'txt'), ('الوحدة', 'c'), ('الحالة', 'c'), ('التوصية', 'c'),
                   ('الكمية', 'c')] + wh_cols + [
                   ('تكلفة الوحدة', 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'), ('سعر البيع بدون ضريبة', 'c'), ('القيمة بسعر البيع', 'c'),
                   ('هامش الربح', 'c'), ('مبيعات الفترة', 'c'), ('متوسط البيع اليومي', 'c'), ('أيام التغطية', 'c'),
                   ('آخر بيع', 'c'), ('أيام بلا بيع', 'c'), ('أول استلام', 'c'), ('آخر استلام', 'c'), ('كمية قادمة', 'c'),
                   ('متوسط العمر (يوم)', 'c'), ('أقدم كمية (يوم)', 'c')] + \
                  [('كمية %s' % lbl, 'c') for lbl in m['bucket_labels']] + \
                  [('قيمة %s' % lbl, 'c') for lbl in m['bucket_labels']] + \
                  [('السيولة المتوقعة (%s)' % cur, 'c'), ('تفصيل التوصية', 'txt')]
        widths = [38, 12, 22, 10, 14, 18, 12] + [12] * (len(headers) - 7)
        widths[-1] = 44
        ws = self._new_sheet('كل الأصناف', widths)
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'جميع الأصناف — البيانات التفصيلية', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'صنف واحد في كل سطر مع جميع المؤشرات · تاريخ المخزون %s' % m['date_to_display'], self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        for i, rw in enumerate(self.d['all_products']):
            vals = [(rw['name'], 'txtb'), (rw['code'], 'txt'), (rw['category'], 'txt'), (rw['uom'], 'c'),
                    (rw['status_label'], 'badge:%s' % rw['status']), (rw['action_label'], 'badge:%s' % rw['action']),
                    (rw['qty'], 'qty')]
            if m['multi_warehouse']:
                vals += [(rw['wh_qty'].get(wh['id'], 0.0), 'qty') for wh in m['warehouses']]
            vals += [(rw['unit_cost'], 'money'), (rw['value'], 'moneyb'), (rw['price'], 'money'), (rw['sale_value'], 'money'),
                     (rw['margin_pct'], 'pct'), (rw['sales_qty'], 'qty'), (rw['avg_daily'], 'dec'), (rw['cover_days'], 'int'),
                     (rw['last_sale_str'], 'c'), (rw['days_since_sale'], 'int'), (rw['first_receipt_str'], 'c'),
                     (rw['last_receipt_str'], 'c'), (rw['incoming_qty'], 'qty'), (rw['avg_age'], 'int'), (rw['max_age'], 'int')]
            vals += [(q, 'qty') for q in rw['bucket_qty']]
            vals += [(v, 'money') for v in rw['bucket_value']]
            vals += [(rw['expected_cash'], 'moneyg'), (rw['action_text'], 'txt')]
            self._write_row(ws, r, vals, i % 2 == 1)
            r += 1
        if self.d['all_products']:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
            # conditional formatting: data bars on avg age and value
            age_col = headers.index(('متوسط العمر (يوم)', 'c'))
            val_col = headers.index(('القيمة بالتكلفة (%s)' % cur, 'c'))
            ws.conditional_format(first, age_col, r - 1, age_col, {'type': 'data_bar', 'bar_color': '#C4A46A', 'bar_solid': True})
            ws.conditional_format(first, val_col, r - 1, val_col, {'type': 'data_bar', 'bar_color': '#1F3D2F', 'bar_solid': True})
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_method(self):
        m = self.m
        self._method_sheet([
            ('الكميات', 'كميات المخزون في المواقع الداخلية للفروع المحددة حتى تاريخ التقرير (%s). المبيعات المسجلة دون رصيد كافٍ لا تدخل في الكميات ولا في القيمة ولا في الأعمار، والاستلام اللاحق يغطيها أولاً ولا يُحتسب منه إلا ما تبقى. الأصناف المؤرشفة التي لا يزال لها رصيد تُعرض مع علامة (مؤرشف).' % m['mode_label']),
            ('التقييم', '%s × الكمية. القيمة البيعية = الكمية × سعر البيع المسجل على الصنف بدون ضريبة القيمة المضافة (تُستبعد تلقائياً إذا كان السعر شاملاً لها).' % m['cost_basis_label']),
            ('أعمار المخزون', 'تُنسب الكمية الحالية في كل فرع إلى آخر استلامات دخلت الفرع (من المورد أو التسويات أو فرع آخر) بدءاً من الأحدث (FIFO)، ويُحسب عمر كل جزء من تاريخ استلامه. الكمية التي لا يقابلها استلام مسجل تُنسب لأقدم استلام معروف.'),
            ('المرتجعات', 'المرتجع المرتبط بحركته الأصلية يُعالج على الحركة الأصلية وبتاريخها: مرتجع المشتريات يخفض كمية الاستلام الأصلي نفسه (لا يُعامل كصرف يستهلك أقدم مخزون)، ومرتجع العميل أو مرتجع الفرع يعيد الكمية بعمرها الأصلي ولا يُعد استلاماً جديداً، ويُخصم من مبيعات تاريخ البيع الأصلي (بما في ذلك مرتجعات نقاط البيع المرتبطة بطلبها الأصلي). المرتجع للمورد غير المرتبط بحركة يخفض آخر الاستلامات السابقة له.'),
            ('حركة البيع', 'صافي التسليمات للعملاء (مبيعات − مرتجعات على تاريخ البيع الأصلي) من حركات المخزون خلال فترة التحليل، وتشمل نقاط البيع وأوامر البيع. متوسط البيع اليومي = مبيعات الفترة ÷ %s يوم. أيام التغطية = الكمية ÷ متوسط البيع اليومي.' % m['sales_days']),
            ('التصنيف', 'نشط: له مبيعات وتغطيته ≤ %s يوم · بطيء الحركة: له مبيعات لكن تغطيته > %s يوم (الفائض = الكمية فوق هذه التغطية) · راكد: بلا بيع خلال آخر %s يوم · جديد: استُلم لأول مرة خلال آخر %s يوم ولم يُبع بعد · نافد وله طلب: رصيده صفر وبيع خلال الفترة.' % (m['slow_cover_days'], m['slow_cover_days'], m['stagnant_days'], m['new_days'])),
            ('التوصيات', 'راكد أكثر من سنة: تصفية فورية · أكثر من 6 أشهر: خصم قوي أو عرض حزمة · أقل من ذلك: عرض ترويجي · لم يُبع منذ استلامه وعمره أقل من فترة الركود: متابعة قبل أي خصم · بطيء الحركة: إيقاف الشراء وتصريف الفائض · نشط بتغطية ≤ %s يوم: إعادة طلب · مخزون بلا حركة في فرع ويُباع في فرع آخر: إعادة توزيع بدلاً من التخفيض.' % m['reorder_cover_days']),
            ('السيولة المتوقعة', 'الكمية × سعر البيع الحالي × (1 − الخصم)، والخصم المطبق لكل صنف هو الأقل بين %s%% وهامش الربح حتى لا يُباع أي صنف تحت التكلفة. للأصناف بطيئة الحركة تُحتسب الكمية الفائضة فقط.' % m['liquidation_discount']),
            ('مؤشر صحة المخزون', '100 − (1.5 × نسبة قيمة الراكد) − (0.75 × نسبة قيمة بطيء الحركة). 75 فأكثر جيد · 50–74 مقبول · 30–49 ضعيف · أقل من 30 حرج.'),
            ('معدل الدوران', '%s ÷ متوسط المخزون، مُسنّناً على 365 يوماً؛ أيام المخزون = 365 ÷ معدل الدوران السنوي.' % m['cogs_basis_label']),
        ])
