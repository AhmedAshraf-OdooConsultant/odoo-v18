# -*- coding: utf-8 -*-
"""Excel export of the inventory AGING report.

Sheets: الملخص (KPIs, info, distribution, by category, by warehouse) · الأصناف (every product,
grouped by category, with the age buckets under merged group headers) · أقدم المخزون · المنهجية.
"""
from .xlsx_mirror import MirrorXlsx, col


class StockAgingXlsx(MirrorXlsx):

    title_ar = 'تقرير أعمار المخزون'
    title_en = 'INVENTORY AGING REPORT'

    def build_report(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur
        show_value = bool(self.w.show_value)
        last = m['last_label']
        li = m['n_buckets'] - 1

        # ============================== الملخص ==============================
        self.sheet('الملخص', desc='المؤشرات ونطاق التقرير · توزيع الأعمار · الأعمار حسب الفئة وحسب المستودع')
        self.header()
        self.kpis([
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money', ''),
            (k['total_qty'], 'إجمالي الكميات', 'qty', ''),
            (k['product_count'], 'عدد الأصناف', 'int', ''),
            (k['last_value'], '%s (%s)' % (last, cur), 'money_red', '%.1f%%' % k['last_pct']),
            (k['max_age'], 'أقدم كمية بالمخزون (يوم)', 'int', ''),
        ])
        self.info([
            ('تاريخ المخزون', m['date_to_display'], 'نوع الأرصدة', m['mode_label']),
            ('المستودعات', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else ''),
             'الفئات العمرية', ' · '.join(m['bucket_labels'])),
            ('نطاق حساب العمر', m['aging_scope_label']),
        ])

        # 1. distribution
        self.section('توزيع أعمار المخزون', 'الكمية والقيمة بالتكلفة لكل فئة عمرية', cols=6)
        self.head([col('الفئة العمرية', 'txt'), col('الكمية'), col('نسبة الكمية'),
                   col('القيمة بالتكلفة (%s)' % cur), col('نسبة القيمة'), col('التوزيع بالقيمة')], freeze=False)
        for i, bk in enumerate(d['aging']['buckets']):
            self.row([(bk['label'], 'txtr' if bk['is_old'] else 'txtb'), (bk['qty'], 'qty'), (bk['pct_qty'], 'pct'),
                      (bk['value'], 'money'), (bk['pct'], 'pct'), (bk['pct'], 'bar:%s' % bk['bar_class'])], i % 2 == 1)
        self.total([('الإجمالي', 'txt'), (k['total_qty'], 'qty'), (100.0, 'pct'), (k['total_value'], 'money'),
                    (100.0, 'pct'), ('', 'blank')])
        self.end_table()

        # 2. by category
        specs = [col('الفئة', 'txt'), col('الأصناف'), col('الكمية'), col('القيمة بالتكلفة (%s)' % cur),
                 col('نسبة القيمة'), col('متوسط العمر (يوم)')] + self.bucket_specs(show_value) + \
            [col('نسبة %s' % last, 'old')]
        self.section('أعمار المخزون حسب الفئة', 'كل فئة مجمّعة من أصنافها', cols=len(specs))
        self.head(specs, freeze=False)
        for i, c in enumerate(d['by_category']):
            self.row([(c['name'], 'txtb'), (c['count'], 'int'), (c['qty'], 'qtyb'), (c['value'], 'moneyb'),
                      (c['pct'], 'pct'), (c['avg_age'], 'int')] +
                     self.bucket_cells(c['bucket_qty'], c['bucket_value'] if show_value else None) +
                     [(c['last_pct'], 'pctr' if c['last_pct'] >= 30 else 'pct')], i % 2 == 1)
        bks = d['aging']['buckets']
        self.total([('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'),
                    (100.0, 'pct'), (k['avg_age'], 'int')] +
                   self.bucket_totals([b['qty'] for b in bks], [b['value'] for b in bks] if show_value else None) +
                   [(k['last_pct'], 'pct')])
        self.end_table()

        # 3. by warehouse
        if m['multi_warehouse'] and m['show_category_aging'] and d['aging_by_warehouse']['rows']:
            self.section('أعمار المخزون حسب المستودع', m['wh_aging_hint'], cols=m['n_buckets'] + 3)
            self.head([col('المستودع', 'txt')] + self.bucket_specs(False) +
                      [col('الإجمالي (%s)' % cur), col('نسبة %s' % last, 'old')], freeze=False)
            for i, ag in enumerate(d['aging_by_warehouse']['rows']):
                self.row([(ag['name'], 'txtb')] + [(v, 'oldm' if j == li else 'money') for j, v in enumerate(ag['values'])] +
                         [(ag['total'], 'moneyb'), (ag['pct_last'], 'pctr' if ag['pct_last'] >= 30 else 'pct')], i % 2 == 1)
            aw = d['aging_by_warehouse']
            self.total([('الإجمالي', 'txt')] + [(v, 'money') for v in aw['totals']] +
                       [(aw['total'], 'money'), (aw['pct_last'], 'pct')])
            self.end_table()

        # ============================== الأصناف ==============================
        self.sheet('الأصناف', desc='كل صنف بكميته وقيمته وتوزيع عمره على الفئات العمرية — مجمّعة حسب فئة المنتج')
        self.header('أعمار المخزون حسب الصنف — مجمّعة حسب الفئة بترتيب ثابت · تاريخ المخزون %s' % m['date_to_display'])
        specs = self.product_specs() + [col('متوسط العمر (يوم)', 'c', 'العمر'), col('أقدم كمية (يوم)', 'c', 'العمر')] + \
            self.bucket_specs(show_value)
        lc = self.product_label_cols()
        self.head(specs, autofilter=True)
        for c in d['by_category']:
            rows = [rw for rw in c['rows'] if rw['qty'] > 0]
            if not rows:
                continue
            cat = [('', 'blank')] * (lc - 1) + [(c['qty'], 'qty'), ('', 'blank'), ('', 'blank'), (c['value'], 'money'),
                                                ('', 'blank'), (c['sale_value'], 'money'), (c['avg_age'], 'int'),
                                                (c['max_age'], 'int')] + \
                self.bucket_totals(c['bucket_qty'], c['bucket_value'] if show_value else None)
            self.cat_row('%s — %s صنف' % (c['name'], '{:,.0f}'.format(c['count'])), cat)
            for i, rw in enumerate(rows):
                self.row(self.product_cells(rw) +
                         [(rw['avg_age'], 'int'), (rw['max_age'], 'intr' if (rw['max_age'] or 0) > m['last_days'] else 'int')] +
                         self.bucket_cells(rw['bucket_qty'], rw['bucket_value'] if show_value else None), i % 2 == 1)
        self.total([('الإجمالي العام', 'txt')] + self.product_totals(k['total_qty'], k['total_value'], k['total_sale_value'])[lc - 1:] +
                   [(k['avg_age'], 'int'), (k['max_age'], 'int')] +
                   self.bucket_totals([b['qty'] for b in bks], [b['value'] for b in bks] if show_value else None),
                   label_cols=lc)
        self.end_table()

        # ============================== أقدم المخزون ==============================
        if d['oldest'] and k['last_value'] > 0:
            self.sheet('أقدم المخزون', desc='أعلى الأصناف قيمةً في الفئة العمرية الأخيرة — أولى المرشحين للمراجعة')
            self.header('أعلى %s صنفاً قيمةً في الفئة العمرية «%s» — أولى المرشحين للمراجعة والتصفية' % (len(d['oldest']), last))
            specs = self.product_specs(with_category=True) + [
                col('الكمية', 'c', last), col('القيمة (%s)' % cur, 'c', last), col('نسبتها من قيمة الصنف', 'c', last),
                col('أقدم كمية (يوم)', 'c', 'العمر والاستلام'), col('آخر استلام', 'c', 'العمر والاستلام')]
            self.head(specs, autofilter=True)
            for i, rw in enumerate(d['oldest']):
                share = (rw['bucket_value'][li] / rw['value'] * 100.0) if rw['value'] else 0.0
                self.row(self.product_cells(rw, with_category=True) +
                         [(rw['bucket_qty'][li], 'qtyr'), (rw['bucket_value'][li], 'moneyr'), (share, 'pct'),
                          (rw['max_age'], 'int'), (rw['last_receipt_str'], 'c')], i % 2 == 1)
            self.end_table()

        # ============================== المنهجية ==============================
        self.method(self.method_common() + [
            ('أعمار المخزون', 'العمر %s. تُنسب الكمية الحالية إلى آخر استلامات دخلت النطاق بدءاً من الأحدث (FIFO)، ويُحسب عمر كل جزء من تاريخ استلامه ثم يُوزع على الفئات العمرية. المبيعات المسجلة دون رصيد لا تظهر في الأعمار، والاستلام اللاحق يغطيها أولاً ولا يُعمَّر من تاريخه إلا ما تبقى (شراء 100 ثم بيع 200 ثم شراء 200 ← يُعمَّر 100 فقط من تاريخ الشراء الثاني). الكمية التي لا يقابلها استلام مسجل تُنسب لأقدم استلام معروف.' % m['aging_scope_label']),
            ('الفئة الأخيرة', '«%s» هي المخزون القديم في هذا التقرير: الكمية التي مضى على استلامها أكثر من %s يوماً، وتظهر بنفس الرقم في المؤشرات وفي جداول الفئات والأصناف.' % (last, m['last_days'])),
            ('متوسط العمر / أقدم كمية', 'متوسط العمر = متوسط مرجح بالكمية لأعمار أجزاء الكمية. أقدم كمية = عمر أقدم جزء لا يزال بالمخزون.'),
        ])
