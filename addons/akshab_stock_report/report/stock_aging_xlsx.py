# -*- coding: utf-8 -*-
"""Excel export of the Akshab inventory AGING report (by category, then by product)."""
from .xlsx_base import AkshabXlsxBase


class StockAgingXlsx(AkshabXlsxBase):

    subtitle = 'INVENTORY AGING REPORT'

    def build_sheets(self):
        self._sheet_summary()
        self._sheet_categories()
        self._sheet_products()
        self._sheet_method()

    # ------------------------------------------------------------------
    def _meta_rows(self):
        m = self.m
        return [
            ('تاريخ المخزون', m['date_to_display'], 'نوع الأرصدة', m['mode_label']),
            ('الفروع', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else ''),
             'الفئات العمرية', ' · '.join(m['bucket_labels'])),
        ]

    def _bucket_headers(self, with_value=True):
        cols = []
        for lbl in self.m['bucket_labels']:
            cols.append(('كمية %s' % lbl, 'c'))
            if with_value:
                cols.append(('قيمة %s' % lbl, 'c'))
        return cols

    def _bucket_values(self, obj, with_value=True):
        vals = []
        last = self.m['n_buckets'] - 1
        for i in range(self.m['n_buckets']):
            vals.append((obj['bucket_qty'][i], 'qty'))
            if with_value:
                vals.append((obj['bucket_value'][i], 'moneyr' if (i == last and obj['bucket_value'][i]) else 'money'))
        return vals

    # ------------------------------------------------------------------
    def _sheet_summary(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        n = m['n_buckets']
        last = m['last_label']
        ws = self._new_sheet('الملخص', [30] + [15] * (2 * n + 6))
        r = self._title_block(ws, 'تقرير أعمار المخزون', self._meta_rows(), span=8)
        r = self._kpi_row(ws, r, [
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money'),
            (k['total_qty'], 'إجمالي الكميات', 'int'),
            (k['product_count'], 'عدد الأصناف', 'int'),
            (k['last_value'], '%s (%s)' % (last, cur), 'money_red'),
            (k['last_pct'], 'نسبة القيمة %s' % last, 'pct'),
            (k['max_age'], 'أقدم كمية بالمخزون (يوم)', 'int'),
        ])
        # 1. bucket distribution
        r = self._section(ws, r, '١', 'توزيع أعمار المخزون', 'الكمية والقيمة بالتكلفة لكل فئة عمرية', span=6)
        r = self._write_header(ws, r, [('الفئة العمرية', 'txt'), ('الكمية', 'c'), ('نسبة الكمية', 'c'),
                                       ('القيمة بالتكلفة (%s)' % cur, 'c'), ('نسبة القيمة', 'c')])
        for i, b in enumerate(d['aging']['buckets']):
            self._write_row(ws, r, [(b['label'], 'txtb'), (b['qty'], 'qty'), (b['pct_qty'], 'pct'),
                                    (b['value'], 'moneyr' if b['is_old'] else 'money'), (b['pct'], 'pct')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي', 'txt'), (k['total_qty'], 'qty'), (100.0, 'pct'), (k['total_value'], 'money'), (100.0, 'pct')])
        r += 2
        # 2. by category matrices (value then qty)
        r = self._section(ws, r, '٢', 'أعمار المخزون حسب الفئة', 'القيمة بالتكلفة ثم الكمية لكل فئة عمرية', span=n + 3)
        for kind in ('value', 'qty'):
            ws.merge_range(r, 0, r, n + 3, 'حسب %s' % ('القيمة (%s)' % cur if kind == 'value' else 'الكمية'), self.f_sub)
            r += 1
            r = self._write_header(ws, r, [('الفئة', 'txt')] + [(lbl, 'c') for lbl in m['bucket_labels']] +
                                   [('الإجمالي', 'c'), ('نسبة القيمة %s' % last, 'c')])
            for i, c in enumerate(d['by_category']):
                vals = c['bucket_value'] if kind == 'value' else c['bucket_qty']
                tot = c['value'] if kind == 'value' else c['qty']
                fmt = 'money' if kind == 'value' else 'qty'
                self._write_row(ws, r, [(c['name'], 'txtb')] + [(v, fmt) for v in vals] +
                                [(tot, 'moneyb' if kind == 'value' else 'qty'), (c['last_pct'], 'pct')], i % 2 == 1)
                r += 1
            buckets = d['aging']['buckets']
            self._write_total(ws, r, [('الإجمالي', 'txt')] +
                              [((b['value'] if kind == 'value' else b['qty']), 'money' if kind == 'value' else 'qty') for b in buckets] +
                              [((k['total_value'] if kind == 'value' else k['total_qty']), 'money' if kind == 'value' else 'qty'), (k['last_pct'], 'pct')])
            r += 2
        # 3. by warehouse
        if m['multi_warehouse'] and m['show_category_aging'] and d['aging_by_warehouse']['rows']:
            r = self._section(ws, r, '٣', 'أعمار المخزون حسب الفرع', 'القيمة بالتكلفة', span=n + 3)
            mat = d['aging_by_warehouse']
            r = self._write_header(ws, r, [('الفرع', 'txt')] + [(lbl, 'c') for lbl in mat['columns']] +
                                   [('الإجمالي', 'c'), ('نسبة القيمة %s' % last, 'c')])
            for i, ag in enumerate(mat['rows']):
                self._write_row(ws, r, [(ag['name'], 'txtb')] + [(v, 'money') for v in ag['values']] +
                                [(ag['total'], 'moneyb'), (ag['pct_last'], 'pct')], i % 2 == 1)
                r += 1
            self._write_total(ws, r, [('الإجمالي', 'txt')] + [(v, 'money') for v in mat['totals']] +
                              [(mat['total'], 'money'), (mat['pct_last'], 'pct')])
            r += 2
        # 4. oldest items (top 10 by value in the last bucket)
        if d['oldest']:
            li = n - 1
            r = self._section(ws, r, '٤', 'أعلى 10 أصناف قيمةً في الفئة العمرية «%s»' % last, 'أولى المرشحين للمراجعة والتصفية', span=8)
            r = self._write_header(ws, r, [('الصنف', 'txt'), ('المرجع الداخلي', 'c'), ('الفئة', 'txt'), ('الوحدة', 'c'), ('الكمية', 'c'),
                                           ('القيمة (%s)' % cur, 'c'), ('كمية %s' % last, 'c'), ('قيمة %s (%s)' % (last, cur), 'c'),
                                           ('نسبتها من قيمة الصنف', 'c'), ('أقدم كمية (يوم)', 'c'), ('آخر استلام', 'c')])
            for i, rw in enumerate(d['oldest']):
                share = (rw['bucket_value'][li] / rw['value'] * 100.0) if rw['value'] else 0.0
                self._write_row(ws, r, [(rw['name'], 'txtb'), (rw['code'], 'c'), (rw['category'], 'txt'), (rw['uom'], 'c'), (rw['qty'], 'qty'),
                                        (rw['value'], 'money'), (rw['bucket_qty'][li], 'qty'), (rw['bucket_value'][li], 'moneyr'),
                                        (share, 'pct'), (rw['max_age'], 'int'), (rw['last_receipt_str'], 'c')], i % 2 == 1)
                r += 1
        ws.freeze_panes(3, 0)

    # ------------------------------------------------------------------
    def _sheet_categories(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        last = m['last_label']
        headers = [('الفئة', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'), ('نسبة القيمة', 'c'),
                   ('متوسط العمر (يوم)', 'c'), ('أقدم كمية (يوم)', 'c')] + self._bucket_headers() + \
                  [('نسبة القيمة %s' % last, 'c')]
        ws = self._new_sheet('حسب الفئة', [30] + [14] * (len(headers) - 1))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'أعمار المخزون حسب الفئة', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'كل فئة مجمّعة من أصنافها · تاريخ المخزون %s' % m['date_to_display'], self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        for i, c in enumerate(d['by_category']):
            self._write_row(ws, r, [(c['name'], 'txtb'), (c['count'], 'int'), (c['qty'], 'qty'), (c['value'], 'moneyb'), (c['pct'], 'pct'),
                                    (c['avg_age'], 'int'), (c['max_age'], 'int')] + self._bucket_values(c) +
                            [(c['last_pct'], 'pct')], i % 2 == 1)
            r += 1
        buckets = d['aging']['buckets']
        tot = [('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'), (100.0, 'pct'),
               (k['avg_age'], 'int'), (k['max_age'], 'int')]
        for b in buckets:
            tot += [(b['qty'], 'qty'), (b['value'], 'money')]
        tot += [(k['last_pct'], 'pct')]
        self._write_total(ws, r, tot)
        if d['by_category']:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_products(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        last = m['last_label']
        li = m['n_buckets'] - 1
        wh_cols = [('كمية %s' % wh['name'], 'c') for wh in m['warehouses']] if m['multi_warehouse'] else []
        headers = [('الصنف', 'txt'), ('المرجع الداخلي', 'c'), ('الفئة', 'txt'), ('الوحدة', 'c'), ('الكمية', 'c')] + wh_cols + \
                  [('تكلفة الوحدة', 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'), ('متوسط العمر (يوم)', 'c'), ('أقدم كمية (يوم)', 'c'),
                   ('أول استلام', 'c'), ('آخر استلام', 'c')] + self._bucket_headers() + \
                  [('نسبة القيمة %s' % last, 'c')]
        ws = self._new_sheet('الأصناف', [40, 14, 22, 10, 12] + [13] * (len(headers) - 5))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'أعمار المخزون حسب الصنف', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'مجمّعة حسب الفئة مع إجمالي لكل فئة · تاريخ المخزون %s' % m['date_to_display'], self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r

        for c in d['by_category']:
            ws.merge_range(r, 0, r, len(headers) - 1, '%s — %s · %s %s · %s: %s %s' % (
                c['name'], self._items(c['count']), '{:,.2f}'.format(c['value']), cur, last, '{:,.2f}'.format(c['last_value']), cur), self.f_sub)
            r += 1
            rows = [rw for rw in c['rows'] if rw['qty'] > 0]
            for i, rw in enumerate(rows):
                vals = [(rw['name'], 'txtb'), (rw['code'], 'c'), (rw['category'], 'txt'), (rw['uom'], 'c'), (rw['qty'], 'qty')]
                if m['multi_warehouse']:
                    vals += [(rw['wh_qty'].get(wh['id'], 0.0), 'qty') for wh in m['warehouses']]
                share = (rw['bucket_value'][li] / rw['value'] * 100.0) if rw['value'] else 0.0
                vals += [(rw['unit_cost'], 'money'), (rw['value'], 'moneyb'), (rw['avg_age'], 'int'), (rw['max_age'], 'int'),
                         (rw['first_receipt_str'], 'c'), (rw['last_receipt_str'], 'c')] + self._bucket_values(rw) + \
                        [(share, 'pct')]
                self._write_row(ws, r, vals, i % 2 == 1)
                r += 1
            tot = [('إجمالي %s' % c['name'], 'txt'), ('', 'blank'), ('', 'blank'), ('', 'blank'), (c['qty'], 'qty')]
            if m['multi_warehouse']:
                tot += [(sum(rw['wh_qty'].get(wh['id'], 0.0) for rw in rows), 'qty') for wh in m['warehouses']]
            tot += [('', 'blank'), (c['value'], 'money'), (c['avg_age'], 'int'), (c['max_age'], 'int'), ('', 'blank'), ('', 'blank')]
            for i in range(m['n_buckets']):
                tot += [(c['bucket_qty'][i], 'qty'), (c['bucket_value'][i], 'money')]
            tot += [(c['last_pct'], 'pct')]
            self._write_total(ws, r, tot)
            r += 1
        # grand total
        buckets = d['aging']['buckets']
        tot = [('الإجمالي العام', 'txt'), ('', 'blank'), ('', 'blank'), ('', 'blank'), (k['total_qty'], 'qty')]
        if m['multi_warehouse']:
            tot += [(sum(rw['wh_qty'].get(wh['id'], 0.0) for rw in d['stocked']), 'qty') for wh in m['warehouses']]
        tot += [('', 'blank'), (k['total_value'], 'money'), (k['avg_age'], 'int'), (k['max_age'], 'int'), ('', 'blank'), ('', 'blank')]
        for b in buckets:
            tot += [(b['qty'], 'qty'), (b['value'], 'money')]
        tot += [(k['last_pct'], 'pct')]
        self._write_total(ws, r, tot)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_method(self):
        m = self.m
        self._method_sheet([
            ('الكميات', 'كميات المخزون في المواقع الداخلية للفروع/المواقع المحددة حتى تاريخ التقرير (%s). الأصناف المؤرشفة التي لا يزال لها رصيد تُعرض مع علامة (مؤرشف).' % m['mode_label']),
            ('التقييم', '%s × الكمية.' % m['cost_basis_label']),
            ('أعمار المخزون', 'تُنسب الكمية الحالية في كل فرع إلى آخر استلامات دخلت الفرع (من المورد أو التسويات أو فرع آخر) بدءاً من الأحدث (FIFO)، ويُحسب عمر كل جزء من تاريخ استلامه، ثم يُوزع على الفئات العمرية: %s. المبيعات المسجلة دون رصيد لا تظهر في الأعمار، والاستلام اللاحق يغطيها أولاً ولا يُعمَّر من تاريخه إلا ما تبقى (شراء 100 ثم بيع 200 ثم شراء 200 ← يُعمَّر 100 فقط من تاريخ الشراء الثاني). الكمية التي لا يقابلها استلام مسجل تُنسب لأقدم استلام معروف.' % ' · '.join(m['bucket_labels'])),
            ('المرتجعات', 'المرتجع المرتبط بحركته الأصلية يُعالج على الحركة الأصلية وبتاريخها: مرتجع المشتريات يخفض كمية الاستلام الأصلي نفسه، ومرتجع العميل أو الفرع يعيد الكمية بعمرها الأصلي ولا يُعد استلاماً جديداً. المرتجع للمورد غير المرتبط بحركة يخفض آخر الاستلامات السابقة له.'),
            ('الفئة الأخيرة', '«%s» هي المخزون القديم في هذا التقرير: الكمية التي مضى على استلامها أكثر من %s يوماً، وتظهر بنفس الرقم في المؤشرات وفي جداول الفئات والأصناف.' % (m['last_label'], m['last_days'])),
            ('متوسط العمر / أقدم كمية', 'متوسط العمر = متوسط مرجح بالكمية لأعمار أجزاء الكمية. أقدم كمية = عمر أقدم جزء لا يزال بالمخزون.'),
        ])

    @staticmethod
    def _items(n):
        from .stock_report_engine import ar_items
        return ar_items(n)
