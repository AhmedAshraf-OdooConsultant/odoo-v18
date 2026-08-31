# -*- coding: utf-8 -*-
"""Excel export of the ITEM STATUS report (stagnant / slow / active).

Sheets: الملخص (KPIs, info, status summary, by category) · one sheet per status with the full
product list · إعادة التوزيع · المنهجية.
"""
from .xlsx_mirror import MirrorXlsx, col


class StockStatusXlsx(MirrorXlsx):

    title_ar = 'تقرير حالة الأصناف'
    title_en = 'STAGNANT · SLOW · ACTIVE ITEMS REPORT'

    def _sale_specs(self):
        return [col('مبيعات الفترة', 'c', 'حركة البيع'), col('متوسط يومي', 'c', 'حركة البيع'),
                col('التغطية (يوم)', 'c', 'حركة البيع'), col('آخر بيع', 'c', 'حركة البيع'),
                col('أيام بلا بيع', 'c', 'حركة البيع'),
                col('آخر استلام', 'c', 'الاستلام والعمر'), col('العمر (يوم)', 'c', 'الاستلام والعمر')]

    def _sale_cells(self, rw):
        return [(rw['sales_qty'], 'qty'), (rw['avg_daily'], 'dec'), (rw['cover_days'], 'int'),
                (rw['last_sale_str'], 'c'), (rw['days_since_sale'], 'int'),
                (rw['last_receipt_str'], 'c'), (rw['avg_age'], 'int')]

    def build_report(self):
        d, k, m, cur, w = self.d, self.k, self.m, self.cur, self.w

        # ============================== الملخص ==============================
        self.sheet('الملخص', desc='المؤشرات ومعايير التصنيف · ملخص الحالات · الحالات حسب الفئة')
        self.header()
        self.kpis([
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money', ''),
            (k['product_count'], 'عدد الأصناف بالمخزون', 'int', ''),
            (k['active_value'], 'نشط (%s) — %s صنف' % (cur, '{:,.0f}'.format(k['active_count'])), 'money', '%.1f%%' % k['active_pct']),
            (k['slow_value'], 'بطيء الحركة (%s) — %s صنف' % (cur, '{:,.0f}'.format(k['slow_count'])), 'money', '%.1f%%' % k['slow_pct']),
            (k['stagnant_value'], 'راكد (%s) — %s صنف' % (cur, '{:,.0f}'.format(k['stagnant_count'])), 'money_red', '%.1f%%' % k['stagnant_pct']),
            (k['out_count'], 'أصناف نافدة لها طلب', 'int', ''),
        ])
        self.info([
            ('تاريخ المخزون', '%s · %s' % (m['date_to_display'], m['mode_label']),
             'فترة تحليل المبيعات', self.period_text(m['sales_from'], m['sales_to'], m['sales_days'])),
            ('المستودعات', m['warehouses_display'], 'المواقع', m['locations_display']),
            ('الفئات', m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else '')),
            ('معايير التصنيف', 'راكد: لم يُبع خلال آخر %s يوم · بطيء الحركة: يُباع لكن تغطيته أكثر من %s يوم · نشط: يُباع وتغطيته مناسبة · نافد وله طلب: رصيده صفر وبيع خلال الفترة · إعادة طلب: تغطية أقل من %s يوم' % (
                m['stagnant_days'], m['slow_cover_days'], m['reorder_cover_days'])),
        ])

        # 1. status summary
        self.section('ملخص الحالات', 'تصنيف كل صنف حسب حركة بيعه خلال فترة التحليل', cols=7)
        self.head([col('الحالة', 'txt'), col('عدد الأصناف'), col('الكمية'), col('القيمة بالتكلفة (%s)' % cur),
                   col('نسبة القيمة'), col('القيمة البيعية (%s)' % cur), col('التوزيع')], freeze=False)
        for i, s in enumerate(d['status_summary']):
            self.row([(s['label'], 'badge:%s' % s['key']), (s['count'], 'int'), (s['qty'], 'qty'), (s['value'], 'money'),
                      (s['pct'], 'pct'), (s['sale_value'], 'money'), (s['pct'], 'bar:%s' % s['bar_class'])], i % 2 == 1)
        st = d['status_total']
        self.total([('الإجمالي', 'txt'), (st['count'], 'int'), (st['qty'], 'qty'), (st['value'], 'money'),
                    (100.0, 'pct'), (st['sale_value'], 'money'), ('', 'blank')])
        self.end_table()

        # 2. by category
        self.section('الحالات حسب الفئة', 'القيمة بالتكلفة لكل حالة داخل كل فئة', cols=11)
        self.head([col('الفئة', 'txt'), col('عدد الأصناف'), col('القيمة (%s)' % cur), col('نسبة القيمة'),
                   col('نشط', 'c', 'القيمة حسب الحالة (%s)' % cur), col('بطيء الحركة', 'c', 'القيمة حسب الحالة (%s)' % cur),
                   col('راكد', 'c', 'القيمة حسب الحالة (%s)' % cur),
                   col('نسبة الراكد'), col('أصناف راكدة'), col('مبيعات الفترة'), col('متوسط العمر (يوم)')], freeze=False)
        for i, c in enumerate(d['by_category']):
            self.row([(c['name'], 'txtb'), (c['count'], 'int'), (c['value'], 'moneyb'), (c['pct'], 'pct'),
                      (c['active_value'], 'money'),
                      (c['slow_value'], 'money'), (c['stagnant_value'], 'moneyr'),
                      (c['stagnant_pct'], 'pctr' if c['stagnant_pct'] >= 30 else 'pct'),
                      (c['stagnant_count'], 'int'), (c['sales_qty'], 'qty'), (c['avg_age'], 'int')], i % 2 == 1)
        self.total([('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_value'], 'money'), (100.0, 'pct'),
                    (k['active_value'], 'money'),
                    (k['slow_value'], 'money'), (k['stagnant_value'], 'money'), (k['stagnant_pct'], 'pct'),
                    (k['stagnant_count'], 'int'), ('', 'blank'), (k['avg_age'], 'int')])
        self.end_table()

        # ============================== one sheet per status ==============================
        for key, sheet, title, flag in (('stagnant', 'الأصناف الراكدة', 'الأصناف الراكدة', w.show_stagnant),
                                        ('slow', 'بطيئة الحركة', 'الأصناف بطيئة الحركة (فائض)', w.show_slow),
                                        ('active', 'الأصناف النشطة', 'الأصناف النشطة', w.show_active),
                                        ('out', 'نافدة لها طلب', 'أصناف نافدة لها طلب', w.show_out_of_stock)):
            sg = d['status_groups'][key]
            if not (flag and sg['count']):
                continue
            self.sheet(sheet, desc='%s — القائمة الكاملة مجمّعة حسب فئة المنتج' % title)
            self.header('%s — %s · مجمّعة حسب الفئة بترتيب ثابت · الأصناف داخل كل فئة حسب القيمة' % (title, sg['items']))
            specs = self.product_specs() + self._sale_specs()
            lc = self.product_label_cols()
            self.head(specs, autofilter=True)
            for g in sg['groups']:
                cat = [('', 'blank')] * (lc - 1) + [(g['qty'], 'qty'), ('', 'blank'), ('', 'blank'), (g['value'], 'money'),
                                                    ('', 'blank'), (g['sale_value'], 'money'), (g['sales_qty'], 'qty')]
                self.cat_row('%s — %s صنف' % (g['name'], '{:,.0f}'.format(g['count'])), cat)
                for i, rw in enumerate(g['rows']):
                    self.row(self.product_cells(rw) + self._sale_cells(rw), i % 2 == 1)
            self.total([('الإجمالي: %s' % sg['items'], 'txt')] +
                       self.product_totals(sg['qty'], sg['value'], sg['sale_value'])[lc - 1:] +
                       [(sg['sales_qty'], 'qty')], label_cols=lc)
            self.end_table()

        # ============================== إعادة التوزيع ==============================
        if w.show_transfers and d['transfers']:
            self.sheet('إعادة التوزيع', desc='اقتراحات نقل المخزون الراكد في مستودع إلى مستودع يبيعه')
            self.header('مخزون بلا حركة في مستودع بينما يُباع في مستودع آخر — النقل بديل عن التخفيض')
            self.transfers_table()

        # ============================== المنهجية ==============================
        self.method(self.method_common() + [
            ('حركة البيع', 'صافي التسليمات للعملاء (مبيعات − مرتجعات على تاريخ البيع الأصلي) خلال الفترة من %s إلى %s ‏(%s يوم)‏. متوسط البيع اليومي = مبيعات الفترة ÷ عدد أيامها. أيام التغطية = الكمية ÷ متوسط البيع اليومي.' % (m['sales_from'], m['sales_to'], m['sales_days'])),
            ('التصنيف', 'نشط: له مبيعات وتغطيته ≤ %s يوم · بطيء الحركة: له مبيعات لكن تغطيته > %s يوم (الفائض = الكمية فوق هذه التغطية) · راكد: بلا بيع خلال آخر %s يوم (ويشمل الأصناف التي لم تُبع منذ استلامها) · نافد وله طلب: رصيده صفر وبيع خلال الفترة.' % (m['slow_cover_days'], m['slow_cover_days'], m['stagnant_days'])),
            ('إعادة التوزيع', 'صنف راكد أو بطيء في مستودع (بلا بيع فيه) بينما يُباع في مستودع آخر تغطيته أقل من %s يوم: يُقترح نقل الكمية التي تكفي المستودع المستقبل نحو %s يوماً من البيع (بحد أقصى الكمية المتاحة في المستودع المرسل) بدلاً من تخفيض سعرها.' % (m['slow_cover_days'], max(30, m['slow_cover_days'] // 2))),
        ])
