# -*- coding: utf-8 -*-
"""Excel export of the Akshab item STATUS report (stagnant / slow / active / out of stock)."""
from .xlsx_base import AkshabXlsxBase
from .stock_report_engine import ar_items

STATUS_SHEETS = [
    ('stagnant', 'الأصناف الراكدة'),
    ('slow', 'بطيئة الحركة'),
    ('active', 'الأصناف النشطة'),
    ('out', 'نافدة لها طلب'),
]


class StockStatusXlsx(AkshabXlsxBase):

    subtitle = 'ITEM STATUS REPORT'

    def build_sheets(self):
        self._sheet_summary()
        flags = {'stagnant': self.w.show_stagnant, 'slow': self.w.show_slow, 'active': self.w.show_active,
                 'out': self.w.show_out_of_stock}
        for key, name in STATUS_SHEETS:
            if flags.get(key, True):
                self._sheet_status(key, name)
        if self.w.show_transfers and self.d['transfers']:
            self._sheet_transfers()
        self._sheet_all()
        self._sheet_method()

    # ------------------------------------------------------------------
    def _meta_rows(self):
        m = self.m
        return [
            ('تاريخ المخزون', m['date_to_display'], 'نوع الأرصدة', m['mode_label']),
            ('المستودعات', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else ''),
             'فترة تحليل المبيعات', 'من %s إلى %s \u200f(%s يوم)\u200f' % (m['sales_from'], m['sales_to'], m['sales_days'])),
            ('معايير التصنيف', 'راكد: بلا بيع خلال %s يوم · بطيء: تغطية > %s يوم · إعادة طلب: تغطية < %s يوم' % (
                m['stagnant_days'], m['slow_cover_days'], m['reorder_cover_days']),
             'تاريخ الطباعة', m['print_date']),
        ]

    def _headers(self):
        cur, m = self.cur, self.m
        wh_cols = [('كمية %s' % wh['name'], 'c') for wh in m['warehouses']] if m['multi_warehouse'] else []
        return [('الصنف', 'txt'), ('الفئة', 'txt'), ('الحالة', 'c'), ('الكمية', 'c'), ('الوحدة', 'c')] + wh_cols + [
            ('تكلفة الوحدة (%s)' % cur, 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'), ('سعر البيع (%s)' % cur, 'c'), ('القيمة البيعية (%s)' % cur, 'c'),
            ('هامش الربح', 'c'),
            ('مبيعات الفترة', 'c'), ('متوسط البيع اليومي', 'c'), ('أيام التغطية', 'c'), ('آخر بيع', 'c'), ('أيام بلا بيع', 'c'),
            ('أول استلام', 'c'), ('آخر استلام', 'c'), ('كمية قادمة', 'c'), ('متوسط العمر (يوم)', 'c'), ('أقدم كمية (يوم)', 'c'),
            ('الفائض (كمية)', 'c'), ('قيمة الفائض', 'c')]

    def _values(self, rw):
        m = self.m
        vals = [(rw['display_name'], 'txtb'), (rw['category'], 'txt'),
                (rw['status_label'], 'badge:%s' % rw['status']), (rw['qty'], 'qty'), (rw['uom'], 'c')]
        if m['multi_warehouse']:
            vals += [(rw['wh_qty'].get(wh['id'], 0.0), 'qty') for wh in m['warehouses']]
        vals += [(rw['unit_cost'], 'money'), (rw['value'], 'moneyb'), (rw['price'], 'money'), (rw['sale_value'], 'money'), (rw['margin_pct'], 'pct'),
                 (rw['sales_qty'], 'qty'), (rw['avg_daily'], 'dec'), (rw['cover_days'], 'int'), (rw['last_sale_str'], 'c'), (rw['days_since_sale'], 'int'),
                 (rw['first_receipt_str'], 'c'), (rw['last_receipt_str'], 'c'), (rw['incoming_qty'], 'qty'), (rw['avg_age'], 'int'), (rw['max_age'], 'int'),
                 (rw['excess_qty'], 'qty'), (rw['excess_value'], 'money')]
        return vals

    # ------------------------------------------------------------------
    def _sheet_summary(self):
        d, k, cur = self.d, self.k, self.cur
        ws = self._new_sheet('الملخص', [30] + [16] * 14)
        r = self._title_block(ws, 'تقرير حالة الأصناف', self._meta_rows(), span=8)
        r = self._kpi_row(ws, r, [
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money'),
            (k['product_count'], 'عدد الأصناف بالمخزون', 'int'),
            (k['active_value'], 'نشط (%s) — %.1f%%' % (cur, k['active_pct']), 'money'),
            (k['slow_value'], 'بطيء الحركة (%s) — %.1f%%' % (cur, k['slow_pct']), 'money'),
            (k['stagnant_value'], 'راكد (%s) — %.1f%%' % (cur, k['stagnant_pct']), 'money_red'),
            (k['stagnant_count'], 'عدد الأصناف الراكدة', 'int'),
            (k['out_count'], 'أصناف نافدة لها طلب', 'int'),
        ])
        r = self._section(ws, r, '١', 'ملخص الحالات', 'تصنيف كل صنف حسب حركة بيعه خلال فترة التحليل', span=6)
        r = self._write_header(ws, r, [('الحالة', 'txt'), ('عدد الأصناف', 'c'), ('الكمية', 'c'), ('القيمة بالتكلفة (%s)' % cur, 'c'),
                                       ('نسبة القيمة', 'c'), ('القيمة بسعر البيع (%s)' % cur, 'c')])
        for i, s in enumerate(d['status_summary']):
            self._write_row(ws, r, [(s['label'], 'badge:%s' % s['key']), (s['count'], 'int'), (s['qty'], 'qty'), (s['value'], 'money'),
                                    (s['pct'], 'pct'), (s['sale_value'], 'money')], i % 2 == 1)
            r += 1
        st = d['status_total']
        self._write_total(ws, r, [('الإجمالي', 'txt'), (st['count'], 'int'), (st['qty'], 'qty'), (st['value'], 'money'), (100.0, 'pct'), (st['sale_value'], 'money')])
        r += 2
        r = self._section(ws, r, '٢', 'الحالات حسب الفئة', 'القيمة بالتكلفة لكل حالة داخل كل فئة', span=10)
        r = self._write_header(ws, r, [('الفئة', 'txt'), ('عدد الأصناف', 'c'), ('القيمة (%s)' % cur, 'c'), ('نشط', 'c'), ('بطيء الحركة', 'c'),
                                       ('راكد', 'c'), ('نسبة الراكد', 'c'), ('أصناف راكدة', 'c'), ('مبيعات الفترة', 'c'), ('متوسط العمر (يوم)', 'c')])
        for i, c in enumerate(d['by_category']):
            self._write_row(ws, r, [(c['name'], 'txtb'), (c['count'], 'int'), (c['value'], 'money'), (c['active_value'], 'money'), (c['slow_value'], 'money'),
                                    (c['stagnant_value'], 'moneyr'), (c['stagnant_pct'], 'pct'), (c['stagnant_count'], 'int'),
                                    (c['sales_qty'], 'qty'), (c['avg_age'], 'int')], i % 2 == 1)
            r += 1
        self._write_total(ws, r, [('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_value'], 'money'), (k['active_value'], 'money'), (k['slow_value'], 'money'),
                                  (k['stagnant_value'], 'money'), (k['stagnant_pct'], 'pct'), (k['stagnant_count'], 'int'), ('', 'blank'), (k['avg_age'], 'int')])
        r += 2
        ws.freeze_panes(3, 0)

    # ------------------------------------------------------------------
    def _sheet_status(self, key, name):
        d, m = self.d, self.m
        rows = d[key]
        headers = self._headers()
        ws = self._new_sheet(name, [44, 22, 16, 12, 10] + [13] * (len(headers) - 5))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, name, self.f_title)
        ws.merge_range(1, 0, 1, 8, '%s · مجمّعة حسب الفئة · تاريخ المخزون %s' % (ar_items(len(rows)), m['date_to_display']), self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        if not rows:
            ws.write(r, 0, 'لا توجد أصناف في هذه الحالة ضمن نطاق التقرير.', self.f_note)
        by_cat = {}
        for rw in rows:
            by_cat.setdefault(rw['category'], []).append(rw)
        for cat_name in sorted(by_cat, key=lambda c: -sum(x['value'] for x in by_cat[c])):
            items = by_cat[cat_name]
            ws.merge_range(r, 0, r, len(headers) - 1, '%s — %s · %s %s' % (cat_name, ar_items(len(items)), '{:,.2f}'.format(sum(x['value'] for x in items)), self.cur), self.f_sub)
            r += 1
            for i, rw in enumerate(items):
                self._write_row(ws, r, self._values(rw), i % 2 == 1)
                r += 1
        if rows:
            tot = [('الإجمالي: %s' % ar_items(len(rows)), 'txt'), ('', 'blank'), ('', 'blank'), (sum(x['qty'] for x in rows), 'qty'), ('', 'blank')]
            if m['multi_warehouse']:
                tot += [(sum(x['wh_qty'].get(wh['id'], 0.0) for x in rows), 'qty') for wh in m['warehouses']]
            tot += [('', 'blank'), (sum(x['value'] for x in rows), 'money'), ('', 'blank'), (sum(x['sale_value'] for x in rows), 'money'), ('', 'blank'),
                    (sum(x['sales_qty'] for x in rows), 'qty'), ('', 'blank'), ('', 'blank'), ('', 'blank'), ('', 'blank'), ('', 'blank'), ('', 'blank'),
                    (sum(x['incoming_qty'] for x in rows), 'qty'), ('', 'blank'), ('', 'blank'), (sum(x['excess_qty'] for x in rows), 'qty'),
                    (sum(x['excess_value'] for x in rows), 'money')]
            self._write_total(ws, r, tot)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_all(self):
        d = self.d
        headers = self._headers()
        ws = self._new_sheet('كل الأصناف', [44, 22, 16, 12, 10] + [13] * (len(headers) - 5))
        ws.set_row(0, 26)
        ws.merge_range(0, 0, 0, 8, 'جميع الأصناف مع حالتها', self.f_title)
        ws.merge_range(1, 0, 1, 8, 'صنف واحد في كل سطر مع جميع المؤشرات · استخدم الفلاتر للتصفية حسب الحالة أو الفئة', self.f_hint)
        r = self._write_header(ws, 3, headers)
        ws.repeat_rows(r - 1)
        first = r
        for i, rw in enumerate(d['all_products']):
            self._write_row(ws, r, self._values(rw), i % 2 == 1)
            r += 1
        if d['all_products']:
            ws.autofilter(first - 1, 0, r - 1, len(headers) - 1)
        ws.freeze_panes(first, 1)

    # ------------------------------------------------------------------
    def _sheet_method(self):
        m = self.m
        self._method_sheet([
            ('الكميات', 'كميات المخزون في المواقع الداخلية للمستودعات/المواقع المحددة حتى تاريخ التقرير (%s). المبيعات المسجلة دون رصيد كافٍ لا تدخل في الكميات ولا في القيمة، والاستلام اللاحق يغطيها أولاً ولا يُحتسب منه إلا ما تبقى.' % m['mode_label']),
            ('التقييم', '%s × الكمية. القيمة البيعية = الكمية × سعر البيع المسجل على الصنف بدون ضريبة القيمة المضافة (تُستبعد تلقائياً إذا كان السعر شاملاً لها).' % m['cost_basis_label']),
            ('حركة البيع', 'صافي التسليمات للعملاء (مبيعات − مرتجعات على تاريخ البيع الأصلي) خلال الفترة من %s إلى %s \u200f(%s يوم)\u200f. متوسط البيع اليومي = مبيعات الفترة ÷ عدد أيامها. أيام التغطية = الكمية ÷ متوسط البيع اليومي.' % (m['sales_from'], m['sales_to'], m['sales_days'])),
            ('التصنيف', 'نشط: له مبيعات وتغطيته ≤ %s يوم · بطيء الحركة: له مبيعات لكن تغطيته > %s يوم (الفائض = الكمية فوق هذه التغطية) · راكد: بلا بيع خلال آخر %s يوم (ويشمل الأصناف التي لم تُبع منذ استلامها) · نافد وله طلب: رصيده صفر وبيع خلال الفترة.' % (m['slow_cover_days'], m['slow_cover_days'], m['stagnant_days'])),
            ('أعمار المخزون', 'العمر %s (FIFO؛ المرتجعات تُعالج على حركتها الأصلية).' % m['aging_scope_label']),
            ('إعادة التوزيع', 'صنف راكد أو بطيء في مستودع (بلا بيع فيه) بينما يُباع في مستودع آخر تغطيته أقل من %s يوم: يُقترح نقل الكمية التي تكفي المستودع المستقبل نحو %s يوماً من البيع (بحد أقصى الكمية المتاحة في المستودع المرسل) بدلاً من تخفيض سعرها.' % (m['slow_cover_days'], max(30, m['slow_cover_days'] // 2))),
        ])
