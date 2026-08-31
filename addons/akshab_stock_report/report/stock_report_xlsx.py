# -*- coding: utf-8 -*-
"""Excel export of the COMPREHENSIVE inventory report.

Sheets: الملخص (KPIs, info, quick read, status summary, aging, by warehouse, by category)
· one sheet per product list (راكد / بطيء / جديد / نشط / نافد) · إعادة التوزيع · خطة التصفية
· المنهجية.
"""
from .xlsx_mirror import MirrorXlsx, col


class StockReportXlsx(MirrorXlsx):

    title_ar = 'تقرير المخزون'
    title_en = 'INVENTORY STATUS REPORT'

    # ------------------------------------------------------------------
    def _aging_matrix(self, title, block, pct_key):
        m, k, cur = self.m, self.k, self.cur
        self.head([col(title, 'txt')] + [col(lbl, 'c', 'القيمة بالتكلفة (%s)' % cur) for lbl in m['bucket_labels']] +
                  [col('الإجمالي'), col('نسبة الأقدم من %s يوم' % m['old_days'])], freeze=False)
        for i, ag in enumerate(block['rows']):
            self.row([(ag['name'], 'txtb')] + [(v, 'money') for v in ag['values']] +
                     [(ag['total'], 'moneyb'), (ag[pct_key], 'pctr' if ag[pct_key] >= 30 else 'pct')], i % 2 == 1)
        self.total([('الإجمالي', 'txt')] + [(v, 'money') for v in block['totals']] +
                   [(block['total'], 'money'), (k['old_pct'], 'pct')])
        self.end_table()

    def _list_sheet(self, sheet, title, rows, extra_specs, extra_cells, totals=None, with_category=True):
        """A product list on its own sheet: standard product block + report-specific columns."""
        if not rows:
            return
        self.sheet(sheet, desc=title)
        self.header(title)
        specs = self.product_specs(with_category=with_category) + extra_specs
        lc = self.product_label_cols(with_category=with_category)
        self.head(specs, autofilter=True)
        for i, r in enumerate(rows):
            self.row(self.product_cells(r, with_category=with_category) + extra_cells(r), i % 2 == 1)
        if totals:
            self.total(totals[0] + self.product_totals(*totals[1], with_category=with_category)[lc - 1:] + totals[2],
                       label_cols=lc)
        self.end_table()

    # ------------------------------------------------------------------
    def build_report(self):
        d, k, m, cur = self.d, self.k, self.m, self.cur

        # ============================== الملخص ==============================
        self.sheet('الملخص', desc='المؤشرات · قراءة سريعة للإدارة · الحالات · الأعمار · حسب المستودع وحسب الفئة')
        self.header()
        self.kpis([
            (k['total_value'], 'قيمة المخزون بالتكلفة (%s)' % cur, 'money', ''),
            (k['product_count'], 'عدد الأصناف بالمخزون', 'int', ''),
            (k['total_qty'], 'إجمالي الكميات', 'qty', ''),
            (k['active_value'], 'مخزون نشط (%s)' % cur, 'money', '%.1f%%' % k['active_pct']),
            (k['slow_value'], 'بطيء الحركة / فائض (%s)' % cur, 'money', '%.1f%%' % k['slow_pct']),
            (k['stagnant_value'], 'مخزون راكد (%s) — %s صنف' % (cur, '{:,.0f}'.format(k['stagnant_count'])), 'money_red', '%.1f%%' % k['stagnant_pct']),
            (k['avg_age'], 'متوسط عمر المخزون (يوم)', 'int', ''),
        ])
        self.info([
            ('تاريخ المخزون', m['date_to_display'], 'نوع الأرصدة', m['mode_label']),
            ('المستودعات', m['warehouses_display'], 'الفئات',
             m['categories_display'] + (' — ' + m['products_display'] if m['products_display'] else '')),
            ('فترة تحليل المبيعات', self.period_text(m['sales_from'], m['sales_to'], m['sales_days']),
             'معيار الركود', 'لم يُبع خلال آخر %s يوم · بطيء الحركة: تغطية أكثر من %s يوم' % (m['stagnant_days'], m['slow_cover_days'])),
            ('مؤشر صحة المخزون', '%s / 100 — %s' % ('{:,.0f}'.format(k['health_score']), k['health_label']),
             'سيولة متوقعة من خطة التصفية', '%s %s (بخصم يصل إلى %s%% دون البيع تحت التكلفة)' % (
                 '{:,.2f}'.format(k['expected_cash']), cur, '{:,.0f}'.format(m['liquidation_discount']))),
            ('معدل دوران المخزون', '%.1f مرة / سنة · أيام المخزون: %s يوم' % (
                k['turnover'], '{:,.0f}'.format(k['dsi']) if k['dsi'] is not None else '-'),
             'تاريخ الطباعة', '%s · %s · %s' % (m['print_date'], m['currency_name'], m['cost_basis_label'])),
        ])
        self.list_block('قراءة سريعة للإدارة', d['insights'][:5])

        # 1. status summary
        self.section('ملخص حالة المخزون', 'تصنيف كل صنف حسب حركة بيعه خلال فترة التحليل', cols=7)
        defs = {
            'active': 'يُباع خلال فترة التحليل وكميته مناسبة لمعدل بيعه',
            'slow': 'يُباع لكن كميته تكفي لأكثر من %s يوماً (فائض مخزون)' % m['slow_cover_days'],
            'stagnant': 'لم يُسجل له أي بيع خلال آخر %s يوماً' % m['stagnant_days'],
            'new': 'استُلم خلال آخر %s يوماً ولم يُبع بعد' % m['new_days'],
        }
        self.head([col('الحالة', 'txt'), col('التعريف', 'txt'), col('عدد الأصناف'), col('الكمية'),
                   col('القيمة بالتكلفة (%s)' % cur), col('النسبة'), col('التوزيع')], freeze=False)
        for i, s in enumerate(d['status_summary']):
            self.row([(s['label'], 'badge:%s' % s['key']), (defs.get(s['key'], ''), 'txt'), (s['count'], 'int'),
                      (s['qty'], 'qty'), (s['value'], 'money'), (s['pct'], 'pct'),
                      (s['pct'], 'bar:%s' % s['bar_class'])], i % 2 == 1)
        st = d['status_total']
        self.total([('الإجمالي', 'txt'), (st['count'], 'int'), (st['qty'], 'qty'), (st['value'], 'money'),
                    (100.0, 'pct'), ('', 'blank')], label_cols=2)
        self.end_table()

        # 2. aging
        self.section('أعمار المخزون', 'العمر %s' % m['aging_scope_label'], cols=5)
        self.head([col('الفئة العمرية', 'txt'), col('الكمية'), col('القيمة بالتكلفة (%s)' % cur), col('النسبة'),
                   col('التوزيع')], freeze=False)
        for i, bk in enumerate(d['aging']['buckets']):
            self.row([(bk['label'], 'txtr' if bk['is_old'] else 'txtb'), (bk['qty'], 'qty'), (bk['value'], 'money'),
                      (bk['pct'], 'pct'), (bk['pct'], 'bar:%s' % bk['bar_class'])], i % 2 == 1)
        ag = d['aging']
        self.total([('الإجمالي', 'txt'), (ag['total_qty'], 'qty'), (ag['total_value'], 'money'), (100.0, 'pct'), ('', 'blank')])
        self.note('متوسط العمر المرجح بالكمية %s يوم، وبالقيمة %s يوم · المخزون الأقدم من %s يوماً يمثل %.1f%% من القيمة (%s %s)، ومنه %.1f%% أقدم من سنة.' % (
            '{:,.0f}'.format(ag['avg_age']), '{:,.0f}'.format(ag['avg_age_value']), m['old_days'],
            k['old_pct'], '{:,.2f}'.format(k['old_value']), cur, k['over_year_pct']))
        self.end_table()
        if m['multi_warehouse'] and d['aging_by_warehouse']['rows']:
            self._aging_matrix('أعمار المخزون حسب المستودع', d['aging_by_warehouse'], 'pct_old')
        if m['show_category_aging'] and d['aging_by_category']['rows']:
            self._aging_matrix('أعمار المخزون حسب الفئة', d['aging_by_category'], 'pct_old')

        # 3. by warehouse
        if d['by_warehouse']:
            self.section('المخزون حسب المستودع', 'القيمة والحالة ومتوسط العمر في كل مستودع', cols=14)
            self.head([col('المستودع', 'txt'), col('عدد الأصناف'), col('الكمية'), col('القيمة (%s)' % cur), col('النسبة'),
                       col('نشط', 'c', 'القيمة حسب الحالة (%s)' % cur), col('بطيء الحركة', 'c', 'القيمة حسب الحالة (%s)' % cur),
                       col('راكد', 'c', 'القيمة حسب الحالة (%s)' % cur), col('نسبة الراكد', 'c', 'القيمة حسب الحالة (%s)' % cur),
                       col('عدد الأصناف', 'c', 'بلا بيع في المستودع'), col('قيمتها (%s)' % cur, 'c', 'بلا بيع في المستودع'),
                       col('مبيعات الفترة'), col('متوسط العمر (يوم)'), col('دوران سنوي')], freeze=False)
            for i, bw in enumerate(d['by_warehouse']):
                self.row([(bw['name'], 'txtb'), (bw['count'], 'int'), (bw['qty'], 'qty'), (bw['value'], 'moneyb'), (bw['pct'], 'pct'),
                          (bw['active_value'], 'money'), (bw['slow_value'], 'money'), (bw['stagnant_value'], 'moneyr'),
                          (bw['stagnant_pct'], 'pctr' if bw['stagnant_pct'] >= 30 else 'pct'),
                          (bw['idle_count'], 'int'), (bw['idle_value'], 'money'), (bw['sales_qty'], 'qty'),
                          (bw['avg_age'], 'int'), (bw['turnover'], 'dec')], i % 2 == 1)
            self.total([('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'),
                        (100.0, 'pct'), (k['active_value'], 'money'), (k['slow_value'], 'money'), (k['stagnant_value'], 'money'),
                        (k['stagnant_pct'], 'pct'), ('', 'blank'), ('', 'blank'), ('', 'blank'), (k['avg_age'], 'int'),
                        (k['turnover'], 'dec')])
            self.note('"بلا بيع في المستودع": أصناف موجودة في المستودع ولم تُبع فيه خلال فترة الركود حتى لو كانت تُباع في مستودع آخر — راجع ورقة إعادة التوزيع.')
            self.end_table()

        # 4. by category
        self.section('المخزون حسب الفئة', 'مرتبة تنازلياً حسب القيمة', cols=13)
        self.head([col('الفئة', 'txt'), col('عدد الأصناف'), col('الكمية'), col('القيمة (%s)' % cur), col('النسبة'),
                   col('نشط', 'c', 'القيمة حسب الحالة (%s)' % cur), col('بطيء الحركة', 'c', 'القيمة حسب الحالة (%s)' % cur),
                   col('راكد', 'c', 'القيمة حسب الحالة (%s)' % cur), col('نسبة الراكد', 'c', 'القيمة حسب الحالة (%s)' % cur),
                   col('أصناف راكدة'), col('مبيعات الفترة'), col('متوسط العمر (يوم)'), col('دوران سنوي')], freeze=False)
        for i, bc in enumerate(d['by_category']):
            self.row([(bc['name'], 'txtb'), (bc['count'], 'int'), (bc['qty'], 'qty'), (bc['value'], 'moneyb'), (bc['pct'], 'pct'),
                      (bc['active_value'], 'money'), (bc['slow_value'], 'money'), (bc['stagnant_value'], 'moneyr'),
                      (bc['stagnant_pct'], 'pctr' if bc['stagnant_pct'] >= 30 else 'pct'), (bc['stagnant_count'], 'int'),
                      (bc['sales_qty'], 'qty'), (bc['avg_age'], 'int'), (bc['turnover'], 'dec')], i % 2 == 1)
        self.total([('الإجمالي', 'txt'), (k['product_count'], 'int'), (k['total_qty'], 'qty'), (k['total_value'], 'money'),
                    (100.0, 'pct'), (k['active_value'], 'money'), (k['slow_value'], 'money'), (k['stagnant_value'], 'money'),
                    (k['stagnant_pct'], 'pct'), (k['stagnant_count'], 'int'), ('', 'blank'), (k['avg_age'], 'int'),
                    (k['turnover'], 'dec')])
        self.end_table()

        # ============================== product sheets ==============================
        liq = '{:,.0f}'.format(m['liquidation_discount'])
        self._list_sheet(
            'الأصناف الراكدة', 'الأصناف الراكدة وتوصيات التصفية — لم تُبع خلال آخر %s يوماً · مرتبة حسب القيمة' % m['stagnant_days'],
            d['stagnant'],
            [col('آخر بيع', 'c', 'حركة البيع'), col('أيام بلا بيع', 'c', 'حركة البيع'), col('العمر (يوم)', 'c', 'حركة البيع'),
             col('أقصى خصم دون خسارة', 'c', 'التصفية'), col('سيولة متوقعة بخصم %s%%' % liq, 'c', 'التصفية'),
             col('التوصية', 'c', 'التصفية')],
            lambda r: [(r['last_sale_str'], 'c'), (r['days_since_sale'], 'int'), (r['avg_age'], 'int'),
                       (r['max_discount'], 'pct'), (r['expected_cash'], 'moneyg'), (r['action_label'], 'badge:%s' % r['action'])],
            totals=([('الإجمالي: %s' % d['totals']['stagnant_items'], 'txt')],
                    (d['totals']['stagnant_qty'], k['stagnant_value'], sum(r['sale_value'] for r in d['stagnant'])),
                    [('', 'blank')] * 4 + [(k['stagnant_cash'], 'money')]))

        t = d['totals']
        self._list_sheet(
            'بطيئة الحركة', 'الأصناف بطيئة الحركة (فائض مخزون) — تكفي لأكثر من %s يوماً · مرتبة حسب قيمة الفائض' % m['slow_cover_days'],
            d['slow'],
            [col('مبيعات الفترة', 'c', 'حركة البيع'), col('متوسط البيع اليومي', 'c', 'حركة البيع'),
             col('أيام التغطية', 'c', 'حركة البيع'),
             col('الكمية', 'c', 'الفائض'), col('القيمة (%s)' % cur, 'c', 'الفائض'),
             col('سيولة متوقعة', 'c', 'الفائض'), col('التوصية', 'c', 'الفائض')],
            lambda r: [(r['sales_qty'], 'qty'), (r['avg_daily'], 'dec'), (r['cover_days'], 'int'),
                       (r['excess_qty'], 'qty'), (r['excess_value'], 'moneyb'), (r['expected_cash'], 'moneyg'),
                       (r['action_label'], 'badge:%s' % r['action'])],
            totals=([('الإجمالي: %s' % t['slow_items'], 'txt')],
                    (t['slow_qty'], k['slow_value'], sum(r['sale_value'] for r in d['slow'])),
                    [('', 'blank')] * 3 + [(t['slow_excess_qty'], 'qty'), (t['slow_excess_value'], 'money'), (t['slow_cash'], 'money')]))

        self._list_sheet(
            'أصناف جديدة', 'الأصناف الجديدة (تحت المتابعة) — استُلمت خلال آخر %s يوماً ولم تُبع بعد' % m['new_days'],
            d['new'],
            [col('أول استلام', 'c', 'الاستلام'), col('أيام منذ الاستلام', 'c', 'الاستلام'), col('التوصية', 'c', 'الاستلام')],
            lambda r: [(r['first_receipt_str'], 'c'), (r['max_age'], 'int'), (r['action_label'], 'badge:%s' % r['action'])])

        if m['show_active']:
            self._list_sheet(
                'الأصناف النشطة', 'الأصناف النشطة (الأكثر حركة) — مرتبة حسب كمية المبيعات خلال فترة التحليل',
                d['active'],
                [col('مبيعات الفترة', 'c', 'حركة البيع'), col('متوسط البيع اليومي', 'c', 'حركة البيع'),
                 col('أيام التغطية', 'c', 'حركة البيع'), col('آخر بيع', 'c', 'حركة البيع'),
                 col('كمية قادمة', 'c', 'التوريد'), col('التوصية', 'c', 'التوريد')],
                lambda r: [(r['sales_qty'], 'qtyb'), (r['avg_daily'], 'dec'),
                           (r['cover_days'], 'intr' if (r['cover_days'] is not None and r['cover_days'] <= m['reorder_cover_days']) else 'int'),
                           (r['last_sale_str'], 'c'), (r['incoming_qty'] if r['incoming_qty'] else None, 'qty'),
                           (r['action_label'], 'badge:%s' % r['action'])],
                totals=([('الإجمالي: %s' % t['active_items'], 'txt')],
                        (t['active_qty'], k['active_value'], sum(r['sale_value'] for r in d['active'])),
                        [(t['active_sales_qty'], 'qty')]))

        if m['show_out_of_stock'] and d['out']:
            self.sheet('نافدة لها طلب', desc='أصناف بيعت خلال الفترة ورصيدها الآن صفر — فرص بيع مفقودة')
            self.header('أصناف بيعت خلال فترة التحليل ورصيدها الآن صفر — فرص بيع مفقودة')
            self.head([col('الصنف', 'txt'), col('الفئة', 'txt'),
                       col('مبيعات الفترة', 'c', 'حركة البيع'), col('متوسط البيع اليومي', 'c', 'حركة البيع'),
                       col('آخر بيع', 'c', 'حركة البيع'), col('آخر استلام', 'c', 'التوريد'),
                       col('كمية قادمة', 'c', 'التوريد'), col('تكلفة الوحدة (%s)' % cur, 'c', 'التوريد'),
                       col('سعر البيع (%s)' % cur, 'c', 'التوريد'), col('التوصية', 'c', 'التوريد')], autofilter=True)
            for i, r in enumerate(d['out']):
                self.row([(r['display_name'], 'name'), (r['category'], 'txt'), (r['sales_qty'], 'qtyb'), (r['avg_daily'], 'dec'),
                          (r['last_sale_str'], 'c'), (r['last_receipt_str'], 'c'),
                          (r['incoming_qty'] if r['incoming_qty'] else None, 'qty'), (r['unit_cost'], 'money'),
                          (r['price'], 'money'), (r['action_label'], 'badge:%s' % r['action'])], i % 2 == 1)
            self.end_table()

        if d['transfers']:
            self.sheet('إعادة التوزيع', desc='اقتراحات نقل المخزون الراكد في مستودع إلى مستودع يبيعه')
            self.header('مخزون بلا حركة في مستودع بينما يُباع في مستودع آخر — النقل بديل عن التخفيض')
            self.transfers_table()

        # ============================== خطة التصفية ==============================
        self.sheet('خطة التصفية', desc='الإجراءات المقترحة والسيولة المتوقعة · أبرز النتائج · مساحة قرار الإدارة')
        self.header('خلاصة التوصيات وخطة التصفية — ما تحتاجه الإدارة لاتخاذ القرار')
        if d['plan']['rows']:
            self.head([col('الإجراء المقترح', 'txt'), col('عدد الأصناف'), col('الكمية'), col('التكلفة (%s)' % cur),
                       col('القيمة بسعر البيع الحالي (%s)' % cur), col('السيولة المتوقعة بعد الخصم (%s)' % cur),
                       col('نسبة الاسترداد من التكلفة')], freeze=False)
            for i, pl in enumerate(d['plan']['rows']):
                self.row([(pl['label'], 'badge:%s' % pl['key']), (pl['count'], 'int'), (pl['qty'], 'qty'), (pl['cost'], 'money'),
                          (pl['sale_value'], 'money'), (pl['expected_cash'], 'moneyg'), (pl['recovery_pct'], 'pct')], i % 2 == 1)
            pt = d['plan']['total']
            self.total([('الإجمالي', 'txt'), (pt['count'], 'int'), (pt['qty'], 'qty'), (pt['cost'], 'money'),
                        (pt['sale_value'], 'money'), (pt['expected_cash'], 'money'), (pt['recovery_pct'], 'pct')])
            self.note('السيولة المتوقعة = الكمية × سعر البيع الحالي × (1 − الخصم)، والخصم المطبق لكل صنف هو الأقل بين %s%% وهامش الربح حتى لا يُباع أي صنف تحت التكلفة. للأصناف بطيئة الحركة تُحتسب الكمية الفائضة فقط.' % liq)
            self.end_table()
        self.list_block('أبرز النتائج', d['insights'])
        self.lines_block('قرار الإدارة / ملاحظات', 4)

        # ============================== المنهجية ==============================
        self.method([
            ('الكميات', 'كميات المخزون في المواقع الداخلية للمستودعات المحددة حتى تاريخ التقرير (%s). المبيعات المسجلة دون رصيد كافٍ لا تدخل في الكميات ولا في القيمة ولا في الأعمار، والاستلام اللاحق يغطيها أولاً ولا يُحتسب منه إلا ما تبقى. الأصناف المؤرشفة لا تظهر في التقرير (الأصناف النشطة فقط).' % m['mode_label']),
            ('التقييم', '%s × الكمية. القيمة البيعية = الكمية × سعر البيع المسجل على الصنف في أودو بدون ضريبة القيمة المضافة (تُستبعد الضريبة تلقائياً إذا كان السعر شاملاً لها).' % m['cost_basis_label']),
            ('أعمار المخزون', 'العمر %s. تُنسب الكمية الحالية إلى آخر استلامات دخلت النطاق بدءاً من الأحدث (FIFO)، ويُحسب عمر كل جزء من تاريخ استلامه. الكمية التي لا يقابلها استلام مسجل تُنسب لأقدم استلام معروف.' % m['aging_scope_label']),
            ('المرتجعات', 'المرتجع المرتبط بحركته الأصلية يُعالج على الحركة الأصلية وبتاريخها: مرتجع المشتريات يخفض كمية الاستلام الأصلي نفسه (لا يُعامل كصرف يستهلك أقدم مخزون)، ومرتجع العميل أو مرتجع المستودع يعيد الكمية بعمرها الأصلي ولا يُعد استلاماً جديداً، ويُخصم من مبيعات تاريخ البيع الأصلي (بما في ذلك مرتجعات نقاط البيع المرتبطة بطلبها الأصلي). المرتجع للمورد غير المرتبط بحركة يخفض آخر الاستلامات السابقة له.'),
            ('حركة البيع', 'صافي التسليمات للعملاء (مبيعات − مرتجعات على تاريخ البيع الأصلي) من حركات المخزون خلال فترة التحليل، وتشمل نقاط البيع وأوامر البيع. متوسط البيع اليومي = مبيعات الفترة ÷ %s يوم. أيام التغطية = الكمية ÷ متوسط البيع اليومي.' % m['sales_days']),
            ('التصنيف', 'نشط: له مبيعات وتغطيته ≤ %s يوم · بطيء الحركة: له مبيعات لكن تغطيته > %s يوم (الفائض = الكمية فوق هذه التغطية) · راكد: بلا بيع خلال آخر %s يوم · جديد: استُلم لأول مرة خلال آخر %s يوم ولم يُبع بعد · نافد وله طلب: رصيده صفر وبيع خلال الفترة.' % (m['slow_cover_days'], m['slow_cover_days'], m['stagnant_days'], m['new_days'])),
            ('التوصيات', 'راكد أكثر من سنة: تصفية فورية · أكثر من 6 أشهر: خصم قوي أو عرض حزمة · أقل من ذلك: عرض ترويجي · لم يُبع منذ استلامه وعمره أقل من فترة الركود: متابعة قبل أي خصم · بطيء الحركة: إيقاف الشراء وتصريف الفائض · نشط بتغطية ≤ %s يوم: إعادة طلب · مخزون بلا حركة في مستودع ويُباع في مستودع آخر: إعادة توزيع بدلاً من التخفيض.' % m['reorder_cover_days']),
            ('مؤشر صحة المخزون', '100 − (1.5 × نسبة قيمة الراكد) − (0.75 × نسبة قيمة بطيء الحركة). 75 فأكثر جيد · 50–74 مقبول · 30–49 ضعيف · أقل من 30 حرج.'),
        ])
