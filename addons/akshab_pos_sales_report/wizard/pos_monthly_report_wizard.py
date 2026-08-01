# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class AkshabPosMonthlyReportWizard(models.TransientModel):
    """التقرير الشهري: يرث الويزارد الأسبوعي (الذي يرث اليومي) فيحصل على
    محرك الحسابات كاملاً - صافي المرتجعات، معالجة الكومبو، الخصومات
    الموحدة - ويضيف الأقسام الشهرية: أداء أسابيع الشهر، مقارنة بالشهر
    السابق، اتجاه آخر 4 أشهر، ومصفوفة الفروع × الأسابيع."""
    _name = 'akshab.pos.monthly.report.wizard'
    _inherit = 'akshab.pos.weekly.report.wizard'
    _description = 'معالج تقرير المبيعات الشهري - أخشاب البخور'

    ARABIC_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                     'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر',
                     'ديسمبر']
    TREND_MONTHS_BACK = 3

    def _default_month_start(self):
        """أول يوم من آخر شهر مكتمل."""
        today = fields.Date.context_today(self)
        first_this = today.replace(day=1)
        return self._prev_month_first(first_this)

    @staticmethod
    def _prev_month_first(first_of_month):
        return (first_of_month - timedelta(days=1)).replace(day=1)

    @staticmethod
    def _next_month_first(first_of_month):
        return (first_of_month.replace(day=28)
                + timedelta(days=4)).replace(day=1)

    month_start = fields.Date(
        string='الشهر', required=True, default=_default_month_start,
        help='اختر أي يوم داخل الشهر المطلوب - يُحتسب الشهر الميلادي كاملاً')

    online_move_ids = fields.Many2many(
        'account.move', string='فواتير المتجر الإلكتروني',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختر فواتير العملاء (وإشعارات الدائن للمرتجعات) التي تمثل '
             'مبيعات قناة Online Store لهذا الشهر - تُعرض قناةً ثالثة '
             'مستقلة في التقرير')
    online_move_prev_ids = fields.Many2many(
        'account.move', relation='akshab_pos_monthly_wiz_prev_move_rel',
        string='فواتير المتجر الإلكتروني (الشهر السابق)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير قناة Online Store للشهر السابق - تُستخدم في '
             'أعمدة «الشهر السابق / التغير / نسبة التغير» حتى تشمل '
             'المقارنة قناة المتجر الإلكتروني أيضاً')
    ONLINE_CHANNEL_NAME = 'Online Store'
    TOP_PRODUCTS_LIMIT = 30
    VIP_MIN_TOTAL = 5000.0

    def _apply_month(self):
        """تطبيع التاريخ المختار إلى حدود شهره الميلادي بتوقيت المستخدم."""
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        for wizard in self:
            if not wizard.month_start:
                continue
            first = wizard.month_start.replace(day=1)
            wizard.month_start = first
            start_local = tz.localize(datetime.combine(first, time.min))
            end_local = tz.localize(datetime.combine(
                self._next_month_first(first), time.min))
            wizard.date_from = start_local.astimezone(
                pytz.utc).replace(tzinfo=None)
            wizard.date_to = end_local.astimezone(
                pytz.utc).replace(tzinfo=None) - timedelta(seconds=1)

    @api.onchange('month_start')
    def _onchange_month_start(self):
        self._apply_month()

    def get_print_report_name(self):
        self.ensure_one()
        first = self.month_start.replace(day=1)
        return 'تقرير المبيعات الشهري - %s %s' % (
            self.ARABIC_MONTHS[first.month - 1], first.year)

    def _month_last_day(self):
        return self._next_month_first(
            self.month_start.replace(day=1)) - timedelta(days=1)

    def _month_weeks(self):
        """أسابيع من 7 أيام تبدأ من اليوم الأول للشهر: كل 7 أيام أسبوع،
        وما تبقى في نهاية الشهر (أكثر من 7 وأقل من 14 يوماً) يُعتبر
        أسبوعاً واحداً بذاته - فيكون الشهر دائماً 4 أسابيع، الأخير منها
        من 7 إلى 10 أيام (تكتمل المجاميع إلى إجمالي الشهر بالضبط)."""
        first = self.month_start.replace(day=1)
        last = self._month_last_day()
        weeks, cur = [], first
        while cur <= last:
            remaining = (last - cur).days + 1
            if remaining < 14:
                weeks.append((cur, last))
                break
            week_end = cur + timedelta(days=6)
            weeks.append((cur, week_end))
            cur = week_end + timedelta(days=1)
        return weeks

    # ------------------------------------------------------------------
    # بيانات التقرير الشهري
    # ------------------------------------------------------------------
    def prepare_monthly_report_data(self):
        self.ensure_one()
        self._apply_month()
        # المحرك اليومي كاملاً (صافي + كومبو + خصومات موحدة)
        data = self.prepare_report_data()

        orders = self._get_orders()
        sales_orders = orders.filtered(lambda o: o.amount_total >= 0)
        refund_orders = orders - sales_orders
        discount_product_ids = self._get_global_discount_product_ids()
        order_discounts = {}
        for order in sales_orders:
            total = sum(amount for _name, amount in
                        self._iter_order_discounts(
                            order, discount_product_ids))
            if total:
                order_discounts[order.id] = total

        first = self.month_start.replace(day=1)
        data['month_label'] = '%s %s' % (
            self.ARABIC_MONTHS[first.month - 1], first.year)
        data['month_from'] = first.strftime('%Y-%m-%d')
        data['month_to'] = self._month_last_day().strftime('%Y-%m-%d')

        data['weekly_rows'] = self._monthly_weekly_breakdown(
            sales_orders, refund_orders, order_discounts)
        data['matrix'] = self._monthly_matrix(sales_orders, refund_orders)
        data['comparison'], data['trend'] = \
            self._monthly_trend_and_comparison(data, discount_product_ids)

        # ---------- قناة المتجر الإلكتروني من فواتير account.move ----------
        online = self._online_dataset()
        if online:
            self._merge_online_into_summary(data, online)
            data['has_data'] = data['has_data'] or bool(online['count'])

        # ---------- بيانات الشهر السابق (لأعمدة المقارنة الموحدة) ----------
        prev = self._prev_month_dataset(discount_product_ids)

        # قوائم الملخص:
        #   - الفواتير/المرتجعات/VIP: قنوات نقاط البيع فقط (فواتير المتجر
        #     الإلكتروني تجميعية فتُستبعد من هذه الأقسام)
        #   - المنتجات/الفئات: تشمل منتجات وفئات فواتير المتجر الإلكتروني
        data['top_invoices'] = {
            'rows': data['section2']['rows'][:10],
            'count': data['section2']['count'],
            'total_fmt': data['section2']['total_fmt'],
        }
        data['top_products'] = self._weekly_top_products(data['section4'])
        self._attach_product_comparison(data['top_products'], prev)
        data['category_summary'] = self._weekly_category_summary(
            data['section4'])
        self._attach_category_comparison(data['category_summary'], prev)
        data['products_detail'] = self._products_detail(
            data['section4'], prev)
        all_partners = sales_orders.mapped('partner_id')
        old_ids = self._get_old_partner_ids(all_partners)
        data['vip'] = self._monthly_vip(sales_orders, old_ids, prev)
        data['common_customers'] = self._common_channel_customers(
            sales_orders, online, old_ids, prev)
        data['channel_comparison'] = self._channel_comparison(
            data, online, prev, sales_orders, refund_orders,
            order_discounts)

        # ---------- الأجزاء التفصيلية: قناة قناة بكامل السجلات ----------
        data['channels'] = self._build_channels(
            data, sales_orders, refund_orders, order_discounts,
            discount_product_ids, old_ids, online)
        # ---------- بيانات الرسوم البيانية ----------
        data['charts'] = self._build_charts(data)
        return data

    # --- القسم الشهري 1: أداء أسابيع الشهر -------------------------------
    def _monthly_weekly_breakdown(self, sales_orders, refund_orders,
                                  order_discounts):
        weeks = self._month_weeks()
        buckets = [{'total': 0.0, 'refunds': 0.0, 'count': 0,
                    'discounts': 0.0, 'partners': set()} for _w in weeks]

        def bucket_of(local_date):
            for i, (w_from, w_to) in enumerate(weeks):
                if w_from <= local_date <= w_to:
                    return buckets[i]
            return None

        for order in sales_orders:
            b = bucket_of(self._local_date(order.date_order))
            if b is None:
                continue
            b['total'] += order.amount_total
            b['count'] += 1
            b['discounts'] += order_discounts.get(order.id, 0.0)
            if order.partner_id:
                b['partners'].add(order.partner_id.id)
        for order in refund_orders:
            b = bucket_of(self._local_date(order.date_order))
            if b is not None:
                b['refunds'] += abs(order.amount_total)
        for b in buckets:
            b['net'] = b['total'] - b['refunds']

        best_net = max((b['net'] for b in buckets), default=0.0)
        rows = []
        for i, ((w_from, w_to), b) in enumerate(zip(weeks, buckets),
                                                start=1):
            rows.append({
                'label': 'الأسبوع %d: من %s إلى %s' % (
                    i, w_from.strftime('%Y-%m-%d'),
                    w_to.strftime('%Y-%m-%d')),
                'range_fmt': '%s - %s' % (w_from.strftime('%m-%d'),
                                          w_to.strftime('%m-%d')),
                'total_fmt': self._fmt_amount(b['net']),
                'count': b['count'],
                'avg_fmt': self._fmt_amount(
                    b['net'] / b['count'] if b['count'] else 0.0),
                'discounts_fmt': self._fmt_amount(b['discounts']),
                'customers': len(b['partners']),
                'is_best': best_net > 0 and b['net'] == best_net,
            })
        t_net = sum(b['net'] for b in buckets)
        t_count = sum(b['count'] for b in buckets)
        all_partners = set()
        for b in buckets:
            all_partners |= b['partners']
        return {
            'rows': rows,
            'total': {
                'total_fmt': self._fmt_amount(t_net),
                'count': t_count,
                'avg_fmt': self._fmt_amount(
                    t_net / t_count if t_count else 0.0),
                'discounts_fmt': self._fmt_amount(
                    sum(b['discounts'] for b in buckets)),
                'customers': len(all_partners),
            },
        }

    # --- القسم الشهري 4: مصفوفة الفروع × الأسابيع ------------------------
    def _monthly_matrix(self, sales_orders, refund_orders):
        weeks = self._month_weeks()
        headers = [
            {'title': 'أسبوع %d' % i,
             'range_fmt': '%s - %s' % (w_from.strftime('%m-%d'),
                                       w_to.strftime('%m-%d'))}
            for i, (w_from, w_to) in enumerate(weeks, start=1)
        ]

        def week_index(local_date):
            for i, (w_from, w_to) in enumerate(weeks):
                if w_from <= local_date <= w_to:
                    return i
            return None

        per_config = {}

        def cfg_vals(order):
            cfg = order.session_id.config_id
            return per_config.setdefault(cfg.id, {
                'name': cfg.name,
                'weeks': [0.0] * len(weeks),
                'total': 0.0,
            })

        for order in sales_orders:
            idx = week_index(self._local_date(order.date_order))
            if idx is None:
                continue
            vals = cfg_vals(order)
            vals['weeks'][idx] += order.amount_total
            vals['total'] += order.amount_total
        for order in refund_orders:
            idx = week_index(self._local_date(order.date_order))
            if idx is None:
                continue
            vals = cfg_vals(order)
            vals['weeks'][idx] -= abs(order.amount_total)
            vals['total'] -= abs(order.amount_total)

        rows = []
        for vals in per_config.values():
            rows.append({
                'name': vals['name'],
                'cells': [self._fmt_amount(v) for v in vals['weeks']],
                'total_fmt': self._fmt_amount(vals['total']),
                'total': vals['total'],
            })
        rows.sort(key=lambda r: r['total'], reverse=True)
        day_totals = [
            self._fmt_amount(sum(v['weeks'][i]
                                 for v in per_config.values()))
            for i in range(len(weeks))
        ]
        grand = sum(v['total'] for v in per_config.values())
        # عرض أعمدة الأسابيع + عمود الإجمالي (اسم الفرع 16%)
        col_width = '{:.2f}%'.format((100.0 - 16.0) / (len(weeks) + 1))
        return {
            'headers': headers,
            'rows': rows,
            'day_totals': day_totals,
            'grand_fmt': self._fmt_amount(grand),
            'col_width': col_width,
        }

    # --- القسمان الشهريان 2 و3: المقارنة بالشهر السابق واتجاه 4 أشهر -----
    def _monthly_trend_and_comparison(self, data, discount_product_ids):
        back = self.TREND_MONTHS_BACK
        first = self.month_start.replace(day=1)
        month_firsts = [first]
        for _i in range(back):
            month_firsts.insert(0, self._prev_month_first(month_firsts[0]))
        # نافذة الأشهر الثلاثة السابقة باستعلام واحد
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        window_from = tz.localize(datetime.combine(
            month_firsts[0], time.min)).astimezone(
            pytz.utc).replace(tzinfo=None)
        prev_orders = self.env['pos.order'].search([
            ('date_order', '>=', window_from),
            ('date_order', '<', self.date_from),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', self.config_ids.ids),
        ])
        buckets = {mf: {'gross': 0.0, 'refunds': 0.0, 'count': 0,
                        'partners': set(), 'discounts': 0.0}
                   for mf in month_firsts[:back]}
        for order in prev_orders:
            local = self._local_date(order.date_order)
            mf = local.replace(day=1)
            b = buckets.get(mf)
            if b is None:
                continue
            if order.amount_total >= 0:
                b['gross'] += order.amount_total
                b['count'] += 1
                if order.partner_id:
                    b['partners'].add(order.partner_id.id)
                b['discounts'] += sum(
                    amount for _name, amount in
                    self._iter_order_discounts(order, discount_product_ids))
            else:
                b['refunds'] += abs(order.amount_total)

        cur_net = data['section1']['grand_total']
        cur_refunds = abs(data['section3']['total'])
        cur = {
            'gross': cur_net + cur_refunds,
            'net': cur_net,
            'refunds': cur_refunds,
            'count': data['section1']['total']['count'],
            'customers': data['section1']['total']['customers'],
            'discounts': data['section6']['grand_total'],
        }

        # ---------- جدول الاتجاه: 3 أشهر سابقة + الشهر الحالي ----------
        trend_rows = []
        prev_net = None
        for i, mf in enumerate(month_firsts):
            if i < back:
                b = buckets[mf]
                net = b['gross'] - b['refunds']
                count = b['count']
                customers, discounts = len(b['partners']), b['discounts']
            else:
                net, count = cur['net'], cur['count']
                customers, discounts = cur['customers'], cur['discounts']
            if prev_net:
                diff_pct = (net - prev_net) / prev_net * 100.0
                growth_fmt = '%{:+.1f}'.format(diff_pct)
                growth_class = ('ak-up' if diff_pct > 0
                                else 'ak-down' if diff_pct < 0 else 'ak-flat')
            else:
                growth_fmt, growth_class = '—', 'ak-flat'
            trend_rows.append({
                'label': '%s %s' % (self.ARABIC_MONTHS[mf.month - 1],
                                    mf.year),
                'total_fmt': self._fmt_amount(net),
                'count': count,
                'avg_fmt': self._fmt_amount(net / count if count else 0.0),
                'customers': customers,
                'discounts_fmt': self._fmt_amount(discounts),
                'growth_fmt': growth_fmt,
                'growth_class': growth_class,
                'is_current': i == back,
            })
            prev_net = net
        trend = {'rows': trend_rows}

        # ---------- المقارنة بالشهر السابق ----------
        pb = buckets[month_firsts[back - 1]]
        p_gross, p_refunds = pb['gross'], pb['refunds']
        p_net = p_gross - p_refunds
        p_count, p_customers = pb['count'], len(pb['partners'])
        p_discounts = pb['discounts']
        metrics = [
            ('إجمالي المبيعات (ر.س)', cur['gross'], p_gross, True),
            ('المرتجعات (ر.س)', cur['refunds'], p_refunds, True),
            ('صافي المبيعات (ر.س)', cur['net'], p_net, True),
            ('عدد الفواتير', cur['count'], p_count, False),
            ('متوسط الفاتورة (ر.س)',
             cur['net'] / cur['count'] if cur['count'] else 0.0,
             p_net / p_count if p_count else 0.0, True),
            ('عدد العملاء', cur['customers'], p_customers, False),
            ('إجمالي الخصومات (ر.س)', cur['discounts'], p_discounts, True),
        ]
        rows = []
        for label, cur_v, prev_v, is_amount in metrics:
            diff = cur_v - prev_v
            fmt = self._fmt_amount if is_amount else (
                lambda v: '{:,.0f}'.format(v))
            if diff > 0:
                arrow, klass = '▲', 'ak-up'
            elif diff < 0:
                arrow, klass = '▼', 'ak-down'
            else:
                arrow, klass = '—', 'ak-flat'
            pct_fmt = ('%{:+.1f}'.format(diff / prev_v * 100.0)
                       if prev_v else '—')
            rows.append({
                'label': label,
                'current_fmt': fmt(cur_v),
                'previous_fmt': fmt(prev_v),
                'diff_fmt': '%s %s' % (arrow, fmt(abs(diff))),
                'pct_fmt': pct_fmt,
                'class': klass,
            })
        return {'rows': rows}, trend

    # =====================================================================
    # قناة المتجر الإلكتروني: توحيد فواتير account.move إلى بنية التقرير
    # =====================================================================
    def _online_dataset(self):
        """يحول الفواتير المختارة يدوياً إلى مجموعة بيانات موحدة:
        فواتير/مرتجعات كاملة، أسابيع، منتجات بالفئات، عملاء، موظفون،
        وخصومات بنود - كلها في الذاكرة مع استعلام واحد لتاريخ العملاء."""
        moves = self.online_move_ids.filtered(
            lambda m: m.state == 'posted'
            and m.move_type in ('out_invoice', 'out_refund'))
        if not moves:
            return None
        first = self.month_start.replace(day=1)
        weeks = self._month_weeks()
        sales = moves.filtered(lambda m: m.move_type == 'out_invoice')
        refunds = moves - sales

        # تاريخ العملاء (جديد/قديم + آخر فاتورة) باستعلام تجميعي واحد
        partner_ids = [p.id for p in moves.mapped('partner_id') if p]
        last_by_partner = {}
        if partner_ids:
            groups = self.env['account.move'].sudo().read_group(
                [('move_type', '=', 'out_invoice'),
                 ('state', '=', 'posted'),
                 ('partner_id', 'in', partner_ids),
                 ('invoice_date', '<', first),
                 ('id', 'not in', moves.ids)],
                ['invoice_date:max'], ['partner_id'])
            for g in groups:
                last_by_partner[g['partner_id'][0]] = g['invoice_date']

        def week_index(d):
            for i, (ws, we) in enumerate(weeks):
                if ws <= d <= we:
                    return i
            return None

        week_buckets = [
            {'gross': 0.0, 'refunds': 0.0, 'count': 0,
             'partners': set(), 'discounts': 0.0}
            for _w in weeks
        ]
        inv_rows, ref_rows = [], []
        cats = {}
        employees = {}
        customers = {}
        gross = net_discounts = 0.0
        partners_all = set()

        def line_discount(line):
            return (line.price_unit * line.quantity * line.discount
                    / 100.0) if line.discount else 0.0

        for m in sales:
            d = m.invoice_date or m.date
            amount = m.amount_total
            gross += amount
            move_disc = 0.0
            for line in m.invoice_line_ids:
                if line.display_type not in (False, 'product'):
                    continue
                product = line.product_id
                pname = product.name if product else (line.name or 'بند حر')
                cname = (product.categ_id.display_name
                         if product and product.categ_id else 'غير مصنّف')
                cid = (product.categ_id.id
                       if product and product.categ_id else 0)
                cat = cats.setdefault(cid, {
                    'name': cname, 'qty': 0.0, 'total': 0.0,
                    'discount': 0.0, 'products': {},
                })
                prod = cat['products'].setdefault(
                    product.id if product else pname, {
                        'name': pname, 'qty': 0.0, 'total': 0.0,
                        'discount': 0.0,
                    })
                ldisc = line_discount(line)
                cat['qty'] += line.quantity
                cat['total'] += line.price_total
                cat['discount'] += ldisc
                prod['qty'] += line.quantity
                prod['total'] += line.price_total
                prod['discount'] += ldisc
                move_disc += ldisc
            net_discounts += move_disc

            partner = m.partner_id
            last = last_by_partner.get(partner.id) if partner else None
            is_new = not last
            days = ''
            if last:
                last_d = fields.Date.to_date(last)
                days = str((d - last_d).days) if d else '-'
                last = fields.Date.to_date(last).strftime('%Y-%m-%d')
            inv_rows.append({
                'date': d.strftime('%Y-%m-%d') if d else '-',
                'number': m.name,
                'pos': self.ONLINE_CHANNEL_NAME,
                'customer': partner.name if partner else '-',
                'phone': (partner.mobile or partner.phone or '-')
                if partner else '-',
                'is_new': 'نعم' if is_new else 'لا',
                'last_inv': last or '-',
                'days': days or '-',
                'total': amount,
                'total_fmt': self._fmt_amount(amount),
            })
            emp = m.invoice_user_id.name if m.invoice_user_id else 'غير محدد'
            ev = employees.setdefault(emp, {
                'name': emp, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            ev['total'] += amount
            ev['count'] += 1
            ev['discounts'] += move_disc
            if partner:
                ev['partners'].add(partner.id)
                partners_all.add(partner.id)
                cv = customers.setdefault(partner.id, {
                    'name': partner.name,
                    'phone': partner.mobile or partner.phone or '-',
                    'is_new': is_new, 'total': 0.0, 'count': 0,
                })
                cv['total'] += amount
                cv['count'] += 1
            if d:
                idx = week_index(d)
                if idx is not None:
                    b = week_buckets[idx]
                    b['gross'] += amount
                    b['count'] += 1
                    b['discounts'] += move_disc
                    if partner:
                        b['partners'].add(partner.id)

        refunds_total = 0.0
        for m in refunds:
            d = m.invoice_date or m.date
            amount = m.amount_total
            refunds_total += amount
            partner = m.partner_id
            ref_rows.append({
                'date': d.strftime('%Y-%m-%d') if d else '-',
                'number': m.name,
                'pos': self.ONLINE_CHANNEL_NAME,
                'customer': partner.name if partner else '-',
                'phone': (partner.mobile or partner.phone or '-')
                if partner else '-',
                'last_inv': '-',
                'total': -amount,
                'total_fmt': self._fmt_amount(-amount),
            })
            emp = m.invoice_user_id.name if m.invoice_user_id else 'غير محدد'
            ev = employees.setdefault(emp, {
                'name': emp, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            ev['total'] -= amount
            if d:
                idx = week_index(d)
                if idx is not None:
                    week_buckets[idx]['refunds'] += amount

        inv_rows.sort(key=lambda r: r['total'], reverse=True)
        ref_rows.sort(key=lambda r: abs(r['total']), reverse=True)
        return {
            'name': self.ONLINE_CHANNEL_NAME,
            'gross': gross, 'refunds': refunds_total,
            'net': gross - refunds_total,
            'count': len(sales), 'partners': partners_all,
            'discounts': net_discounts,
            'inv_rows': inv_rows, 'ref_rows': ref_rows,
            'week_buckets': week_buckets, 'weeks': weeks,
            'cats': cats, 'employees': employees, 'customers': customers,
        }

    # --- دمج الأونلاين في أقسام الملخص التنفيذي --------------------------
    def _merge_online_into_summary(self, data, online):
        net = online['net']
        # KPIs
        k = data['kpis']
        cur_net = data['section1']['grand_total'] + net
        cur_refunds = abs(data['section3']['total']) + online['refunds']
        count = data['section1']['total']['count'] + online['count']
        k['gross_fmt'] = self._fmt_amount(cur_net + cur_refunds)
        k['refunds_fmt'] = self._fmt_amount(cur_refunds)
        k['net_fmt'] = self._fmt_amount(cur_net)
        k['invoices'] = count
        k['avg_fmt'] = self._fmt_amount(cur_net / count if count else 0.0)
        k['discounts_fmt'] = self._fmt_amount(
            data['section6']['grand_total'] + online['discounts'])
        # القسم 1: صف القناة + إعادة النسب والإجماليات
        rows = data['section1']['rows']
        new_c = sum(1 for c in online['customers'].values() if c['is_new'])
        rows.append({
            'name': online['name'],
            'total': net, 'total_fmt': self._fmt_amount(net),
            'share_fmt': '', 'count': online['count'],
            'avg_fmt': self._fmt_amount(
                net / online['count'] if online['count'] else 0.0),
            'discounts_fmt': self._fmt_amount(online['discounts']),
            'customers': len(online['partners']),
            'new': new_c, 'old': len(online['partners']) - new_c,
        })
        rows.sort(key=lambda r: r.get('total', 0.0), reverse=True)
        for r in rows:
            r['share_fmt'] = '%{:.1f}'.format(
                r.get('total', 0.0) / cur_net * 100.0 if cur_net else 0.0)
        t = data['section1']['total']
        data['section1']['grand_total'] = cur_net
        t['total_fmt'] = self._fmt_amount(cur_net)
        t['count'] = count
        t['avg_fmt'] = self._fmt_amount(cur_net / count if count else 0.0)
        t['discounts_fmt'] = k['discounts_fmt']
        t['customers'] += len(online['partners'])
        t['new'] = t.get('new', 0) + new_c
        t['old'] = t.get('old', 0) + (len(online['partners']) - new_c)
        # القسمان 2 و3 (الفواتير والمرتجعات) يبقيان لقنوات نقاط البيع فقط:
        # فواتير المتجر الإلكتروني تجميعية فلا تُدمج في قوائم الفواتير
        # (أعلى 10 فواتير / فواتير المرتجعات / عملاء VIP)
        # القسم 4 (منتجات/فئات): دمج تجميعي ثم يعاد التلخيص لاحقاً
        self._merge_online_products(data['section4'], online['cats'])
        # أداء الأسابيع والمصفوفة
        self._rebuild_weekly_rows(data, online)
        self._append_matrix_row(data, online)
        # الموظفون والخصومات
        emp_rows = self._online_employee_rows(online)
        data['section5']['configs'].append({
            'name': online['name'], 'rows': emp_rows,
            'subtotal': self._employee_subtotal(emp_rows, online),
        })
        if online['discounts']:
            d_rows = [{
                'name': 'خصومات بنود الفواتير',
                'total_fmt': self._fmt_amount(online['discounts']),
                'count': sum(1 for m_r in online['inv_rows'] if m_r),
                'avg_fmt': self._fmt_amount(
                    online['discounts'] / online['count']
                    if online['count'] else 0.0),
            }]
            data['section6']['configs'].append({
                'name': online['name'], 'rows': d_rows,
                'subtotal_fmt': self._fmt_amount(online['discounts']),
                'subtotal_count': online['count'],
                'subtotal_avg_fmt': d_rows[0]['avg_fmt'],
            })
            data['section6']['grand_total'] += online['discounts']
            data['section6']['total_fmt'] = self._fmt_amount(
                data['section6']['grand_total'])

    def _merge_online_products(self, section4, cats):
        """يدمج تجميعات فئات/منتجات الأونلاين في بنية القسم الرابع الخام."""
        # القسم الرابع مبني كصفوف جاهزة؛ نعيد بناء صفوفه بعد إضافة الأونلاين
        by_name = {c['name']: c for c in section4['categories']}
        for cat in cats.values():
            row = by_name.get(cat['name'])
            prods_fmt = [{
                'name': p['name'], 'qty': p['qty'],
                'qty_fmt': self._fmt_qty(p['qty']),
                'avg_fmt': self._fmt_amount(
                    p['total'] / p['qty'] if p['qty'] else 0.0),
                'discount_fmt': self._fmt_amount(p['discount']),
                'total': p['total'],
                'total_fmt': self._fmt_amount(p['total']),
            } for p in sorted(cat['products'].values(),
                              key=lambda x: x['total'], reverse=True)]
            if row is None:
                row = {
                    'name': cat['name'], 'qty': cat['qty'],
                    'qty_fmt': self._fmt_qty(cat['qty']),
                    'avg_fmt': self._fmt_amount(
                        cat['total'] / cat['qty'] if cat['qty'] else 0.0),
                    'discount_fmt': self._fmt_amount(cat['discount']),
                    'total': cat['total'],
                    'total_fmt': self._fmt_amount(cat['total']),
                    'product_count': len(prods_fmt),
                    'products': prods_fmt,
                }
                section4['categories'].append(row)
            else:
                q = row.get('qty', 0.0) + cat['qty']
                tot = row.get('total', 0.0) + cat['total']
                row['qty'] = q
                row['total'] = tot
                row['qty_fmt'] = self._fmt_qty(q)
                row['total_fmt'] = self._fmt_amount(tot)
                row['avg_fmt'] = self._fmt_amount(tot / q if q else 0.0)
                existing = {p['name']: p for p in row['products']}
                for p in prods_fmt:
                    e = existing.get(p['name'])
                    if e is None:
                        row['products'].append(p)
                    else:
                        eq = e.get('qty', 0.0) + p['qty']
                        et = e.get('total', 0.0) + p['total']
                        e['qty'], e['total'] = eq, et
                        e['qty_fmt'] = self._fmt_qty(eq)
                        e['total_fmt'] = self._fmt_amount(et)
                        e['avg_fmt'] = self._fmt_amount(
                            et / eq if eq else 0.0)
                row['products'].sort(
                    key=lambda p: p.get('total', 0.0), reverse=True)
                row['product_count'] = len(row['products'])
        section4['categories'].sort(
            key=lambda c: c.get('total', 0.0), reverse=True)
        tq = sum(c.get('qty', 0.0) for c in section4['categories'])
        tt = sum(c.get('total', 0.0) for c in section4['categories'])
        section4['total_qty_fmt'] = self._fmt_qty(tq)
        section4['total_fmt'] = self._fmt_amount(tt)
        section4['total_avg_fmt'] = self._fmt_amount(tt / tq if tq else 0.0)

    def _rebuild_weekly_rows(self, data, online):
        rows = data['weekly_rows']['rows']
        nets = []
        for i, row in enumerate(rows):
            add = 0.0
            if i < len(online['week_buckets']):
                b = online['week_buckets'][i]
                add = b['gross'] - b['refunds']
                row['count'] += b['count']
                row['customers'] += len(b['partners'])
            nets.append((row, add))
        # صافي كل أسبوع الحالي غير محفوظ خاماً؛ نعيد اشتقاقه من النص المنسق
        for row, add in nets:
            cur = float(row['total_fmt'].replace(',', ''))
            new = cur + add
            row['total_fmt'] = self._fmt_amount(new)
            row['avg_fmt'] = self._fmt_amount(
                new / row['count'] if row['count'] else 0.0)
            row['_net_val'] = new
        best = max((r['_net_val'] for r, _a in nets), default=0.0)
        for row, _a in nets:
            row['is_best'] = best > 0 and row['_net_val'] == best
        t = data['weekly_rows']['total']
        tot = sum(r['_net_val'] for r, _a in nets)
        cnt = sum(r['count'] for r, _a in nets)
        t['total_fmt'] = self._fmt_amount(tot)
        t['count'] = cnt
        t['avg_fmt'] = self._fmt_amount(tot / cnt if cnt else 0.0)
        t['customers'] = data['section1']['total']['customers']

    def _append_matrix_row(self, data, online):
        m = data['matrix']
        cells_raw = [b['gross'] - b['refunds']
                     for b in online['week_buckets']]
        cells_raw = cells_raw[:len(m['headers'])]
        while len(cells_raw) < len(m['headers']):
            cells_raw.append(0.0)
        m['rows'].append({
            'name': online['name'],
            'cells': [self._fmt_amount(v) for v in cells_raw],
            'total': sum(cells_raw),
            'total_fmt': self._fmt_amount(sum(cells_raw)),
        })
        m['rows'].sort(key=lambda r: r.get('total', 0.0), reverse=True)
        day_vals = []
        for i in range(len(m['headers'])):
            base = float(m['day_totals'][i].replace(',', ''))
            day_vals.append(base + cells_raw[i])
        m['day_totals'] = [self._fmt_amount(v) for v in day_vals]
        m['grand_fmt'] = self._fmt_amount(sum(day_vals))

    def _online_employee_rows(self, online):
        rows = []
        for ev in sorted(online['employees'].values(),
                         key=lambda e: e['total'], reverse=True):
            rows.append({
                'name': ev['name'], 'total': ev['total'],
                'total_fmt': self._fmt_amount(ev['total']),
                'count': ev['count'],
                'avg_fmt': self._fmt_amount(
                    ev['total'] / ev['count'] if ev['count'] else 0.0),
                'discounts_fmt': self._fmt_amount(ev['discounts']),
                'customers': len(ev['partners']),
                'new': 0, 'old': len(ev['partners']),
            })
        return rows

    def _employee_subtotal(self, rows, online):
        tot = sum(r['total'] for r in rows)
        cnt = sum(r['count'] for r in rows)
        new_c = sum(1 for c in online['customers'].values() if c['is_new'])
        return {
            'total_fmt': self._fmt_amount(tot), 'count': cnt,
            'avg_fmt': self._fmt_amount(tot / cnt if cnt else 0.0),
            'discounts_fmt': self._fmt_amount(online['discounts']),
            'customers': len(online['partners']),
            'new': new_c, 'old': len(online['partners']) - new_c,
        }

    # =====================================================================
    # بيانات الشهر السابق + أعمدة المقارنة الموحدة
    # =====================================================================
    @staticmethod
    def _phone_key(phone):
        """مفتاح موحّد لمطابقة العملاء برقم الهاتف عبر القنوات: أرقام
        فقط، وآخر 9 أرقام - يوحّد 05xxxxxxxx مع +966 5xxxxxxxx."""
        if not phone:
            return None
        digits = ''.join(ch for ch in str(phone) if ch.isdigit())
        if len(digits) < 7:
            return None
        return digits[-9:]

    def _channel_metrics(self, sales_orders, refund_orders,
                         order_discounts):
        """مؤشرات كل قناة نقاط بيع: إجمالي/مرتجعات/عدد فواتير/عملاء/
        خصومات - تُستخدم لجدول المقارنة بالشهر السابق حسب القناة."""
        per = {}

        def slot(name):
            return per.setdefault(name, {
                'gross': 0.0, 'refunds': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })

        for order in sales_orders:
            vals = slot(order.session_id.config_id.name)
            vals['gross'] += order.amount_total
            vals['count'] += 1
            vals['discounts'] += order_discounts.get(order.id, 0.0)
            if order.partner_id:
                vals['partners'].add(order.partner_id.id)
        for order in refund_orders:
            slot(order.session_id.config_id.name)['refunds'] += \
                abs(order.amount_total)
        return per

    def _prev_month_dataset(self, discount_product_ids):
        """مجاميع الشهر السابق: مؤشرات كل قناة، إجمالي كل منتج وفئة،
        وإجمالي إنفاق كل عميل (بالمعرف وبرقم الهاتف الموحّد) - لتغذية
        أعمدة «الشهر السابق / التغير / نسبة التغير» في أقسام الملخص،
        مع دمج فواتير المتجر الإلكتروني للشهر السابق إن اختيرت."""
        first = self.month_start.replace(day=1)
        prev_first = self._prev_month_first(first)
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        d_from = tz.localize(datetime.combine(
            prev_first, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        d_to = tz.localize(datetime.combine(
            first, time.min)).astimezone(pytz.utc).replace(tzinfo=None) \
            - timedelta(seconds=1)
        orders = self.env['pos.order'].search([
            ('date_order', '>=', d_from),
            ('date_order', '<=', d_to),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', self.config_ids.ids),
        ])
        sales = orders.filtered(lambda o: o.amount_total >= 0)
        refunds = orders - sales

        prev_discounts = {}
        for order in sales:
            total = sum(amount for _name, amount in
                        self._iter_order_discounts(
                            order, discount_product_ids))
            if total:
                prev_discounts[order.id] = total
        channel_metrics = self._channel_metrics(
            sales, refunds, prev_discounts)

        customers, customers_by_phone = {}, {}

        def add_customer(partner, amount):
            customers[partner.id] = customers.get(
                partner.id, 0.0) + amount
            key = self._phone_key(partner.mobile or partner.phone)
            if key:
                customers_by_phone[key] = customers_by_phone.get(
                    key, 0.0) + amount

        for order in sales:
            if order.partner_id:
                add_customer(order.partner_id, order.amount_total)

        products_ch, categories_ch, _pq, _cq = \
            self._pos_channel_product_totals(orders, discount_product_ids)

        # فواتير المتجر الإلكتروني للشهر السابق (اختيارية)
        moves = self.online_move_prev_ids.filtered(
            lambda m: m.state == 'posted'
            and m.move_type in ('out_invoice', 'out_refund'))
        online_m = {'gross': 0.0, 'refunds': 0.0, 'count': 0,
                    'partners': set(), 'discounts': 0.0}
        for m in moves:
            if m.move_type == 'out_refund':
                online_m['refunds'] += m.amount_total
                continue
            online_m['gross'] += m.amount_total
            online_m['count'] += 1
            if m.partner_id:
                online_m['partners'].add(m.partner_id.id)
                add_customer(m.partner_id, m.amount_total)
            for line in m.invoice_line_ids:
                if line.display_type not in (False, 'product'):
                    continue
                product = line.product_id
                pname = product.name if product else (line.name or 'بند حر')
                cname = (product.categ_id.display_name
                         if product and product.categ_id else 'غير مصنّف')
                pmap = products_ch.setdefault(pname, {})
                pmap[self.ONLINE_CHANNEL_NAME] = pmap.get(
                    self.ONLINE_CHANNEL_NAME, 0.0) + line.price_total
                cmap = categories_ch.setdefault(cname, {})
                cmap[self.ONLINE_CHANNEL_NAME] = cmap.get(
                    self.ONLINE_CHANNEL_NAME, 0.0) + line.price_total
                if line.discount:
                    online_m['discounts'] += (
                        line.price_unit * line.quantity
                        * line.discount / 100.0)
        if moves:
            channel_metrics[self.ONLINE_CHANNEL_NAME] = online_m

        return {
            'channel_metrics': channel_metrics,
            'customers': customers,
            'customers_by_phone': customers_by_phone,
            'products': {n: sum(m.values())
                         for n, m in products_ch.items()},
            'categories': {n: sum(m.values())
                           for n, m in categories_ch.items()},
            'products_ch': products_ch,
            'categories_ch': categories_ch,
            'has_online': bool(moves),
        }

    def _cmp_vals(self, cur, prev, has_prev=True, fmt=None):
        """أعمدة المقارنة الموحدة (نفس فكرة قسم المقارنة بالشهر السابق):
        الشهر السابق / التغير مع السهم / نسبة التغير مع لون الاتجاه."""
        if not has_prev:
            return {'prev_fmt': '—', 'diff_fmt': '—',
                    'pct_fmt': '—', 'cmp_class': 'ak-flat'}
        fmt = fmt or self._fmt_amount
        diff = cur - prev
        if diff > 0:
            arrow, klass = '▲', 'ak-up'
        elif diff < 0:
            arrow, klass = '▼', 'ak-down'
        else:
            arrow, klass = '—', 'ak-flat'
        return {
            'prev_fmt': fmt(prev),
            'diff_fmt': '%s %s' % (arrow, fmt(abs(diff))),
            'pct_fmt': ('%{:+.1f}'.format(diff / prev * 100.0)
                        if prev else '—'),
            'cmp_class': klass,
        }

    # --- القسم ٢: مقارنة بالشهر السابق - القنوات أعمدة ------------------
    COMPARISON_METRICS = [
        ('gross', 'إجمالي المبيعات (ر.س)', True),
        ('refunds', 'المرتجعات (ر.س)', True),
        ('net', 'صافي المبيعات (ر.س)', True),
        ('count', 'عدد الفواتير', False),
        ('avg', 'متوسط الفاتورة (ر.س)', True),
        ('customers', 'عدد العملاء', False),
        ('discounts', 'إجمالي الخصومات (ر.س)', True),
    ]

    @staticmethod
    def _metric_val(metrics, key):
        if not metrics:
            return 0.0
        if key == 'net':
            return metrics['gross'] - metrics['refunds']
        if key == 'avg':
            net = metrics['gross'] - metrics['refunds']
            return net / metrics['count'] if metrics['count'] else 0.0
        if key == 'customers':
            return len(metrics['partners'])
        return metrics[key]

    @staticmethod
    def _fmt_amount0(value):
        """تنسيق مبلغ بلا كسور (لأقرب ريال) للجداول العريضة الموزعة
        على القنوات حتى تتسع الأعمدة الكثيرة في عرض الصفحة."""
        return '{:,.0f}'.format(value)

    def _channel_comparison(self, data, online, prev,
                            sales_orders, refund_orders, order_discounts):
        """جدول المقارنة: القنوات أعمدة + عمود الإجمالي، ولكل مؤشر
        (من إجمالي المبيعات إلى إجمالي الخصومات) شريط عنوان وتحته
        أربعة صفوف: هذا الشهر / الشهر السابق / التغير / نسبة التغير."""
        names = [c.name for c in self.config_ids]
        cur = self._channel_metrics(
            sales_orders, refund_orders, order_discounts)
        if online:
            names.append(online['name'])
            cur[online['name']] = {
                'gross': online['gross'], 'refunds': online['refunds'],
                'count': online['count'], 'partners': online['partners'],
                'discounts': online['discounts'],
            }
        prev_m = prev['channel_metrics']

        def totals(mapping):
            agg = {'gross': 0.0, 'refunds': 0.0, 'count': 0,
                   'partners': set(), 'discounts': 0.0}
            for n in names:
                m = mapping.get(n)
                if not m:
                    continue
                agg['gross'] += m['gross']
                agg['refunds'] += m['refunds']
                agg['count'] += m['count']
                agg['discounts'] += m['discounts']
                agg['partners'] |= set(m['partners'])
            return agg

        cur_tot, prev_tot = totals(cur), totals(prev_m)
        columns = [(n, cur.get(n), prev_m.get(n)) for n in names]
        columns.append(('الإجمالي', cur_tot, prev_tot))

        int_fmt = (lambda v: '{:,.0f}'.format(v))
        metrics_out = []
        for key, label, is_amount in self.COMPARISON_METRICS:
            fmt = self._fmt_amount if is_amount else int_fmt
            row_cur = {'label': 'هذا الشهر', 'cells': []}
            row_prev = {'label': 'الشهر السابق', 'cells': []}
            row_diff = {'label': 'التغير', 'cells': []}
            row_pct = {'label': 'نسبة التغير', 'cells': []}
            for name, cm, pm in columns:
                cv = self._metric_val(cm, key)
                pv = self._metric_val(pm, key)
                online_unknown = (
                    online and not prev['has_online']
                    and name == online['name'])
                c = self._cmp_vals(
                    cv, pv, has_prev=not online_unknown, fmt=fmt)
                row_cur['cells'].append({'text': fmt(cv), 'class': ''})
                row_prev['cells'].append(
                    {'text': c['prev_fmt'], 'class': ''})
                row_diff['cells'].append(
                    {'text': c['diff_fmt'], 'class': c['cmp_class']})
                row_pct['cells'].append(
                    {'text': c['pct_fmt'], 'class': c['cmp_class']})
            metrics_out.append({
                'label': label,
                'rows': [row_cur, row_prev, row_diff, row_pct],
            })
        headers = names + ['الإجمالي']
        return {
            'headers': headers,
            'metrics': metrics_out,
            'col_span': len(headers) + 1,
            'col_width': '{:.2f}%'.format((100.0 - 18.0) / len(headers)),
            'online_note': bool(online) and not prev['has_online'],
        }

    # --- توزيع مبيعات المنتجات/الفئات على قنوات البيع --------------------
    def _pos_channel_product_totals(self, orders, discount_product_ids):
        """{اسم المنتج: {اسم القناة: الإجمالي}} و{اسم الفئة: {القناة:
        الإجمالي}} لقنوات نقاط البيع - بنفس منطق القسم الرابع (استبعاد
        بنود الخصم العام والمكافآت ومعالجة الكومبو) عبر استدعائه لكل
        قناة على حدة."""
        prod_ch, cat_ch = {}, {}
        prod_qty_ch, cat_qty_ch = {}, {}

        def bump(mapping, key, channel, value):
            cmap = mapping.setdefault(key, {})
            cmap[channel] = cmap.get(channel, 0.0) + value

        for cfg in self.config_ids:
            ch_orders = orders.filtered(
                lambda o, c=cfg: o.session_id.config_id.id == c.id)
            if not ch_orders:
                continue
            p4 = self._prepare_section_products(
                ch_orders, discount_product_ids)
            for cat in p4['categories']:
                bump(cat_ch, cat['name'], cfg.name, cat['total'])
                bump(cat_qty_ch, cat['name'], cfg.name, cat['qty'])
                for p in cat['products']:
                    bump(prod_ch, p['name'], cfg.name, p['total'])
                    bump(prod_qty_ch, p['name'], cfg.name, p['qty'])
        return prod_ch, cat_ch, prod_qty_ch, cat_qty_ch

    @staticmethod
    def _add_online_channel_products(prod_ch, cat_ch, prod_qty_ch,
                                     cat_qty_ch, cats, channel_name):
        """يضيف تجميعات منتجات/فئات المتجر الإلكتروني (مبالغ وكميات)
        إلى خرائط التوزيع على القنوات تحت اسم قناة الأونلاين."""
        def bump(mapping, key, value):
            cmap = mapping.setdefault(key, {})
            cmap[channel_name] = cmap.get(channel_name, 0.0) + value

        for cat in cats.values():
            bump(cat_ch, cat['name'], cat['total'])
            bump(cat_qty_ch, cat['name'], cat['qty'])
            for p in cat['products'].values():
                bump(prod_ch, p['name'], p['total'])
                bump(prod_qty_ch, p['name'], p['qty'])

    # --- مقارنات المنتجات والفئات ----------------------------------------
    def _attach_product_comparison(self, top_products, prev):
        for row in top_products['rows']:
            row.update(self._cmp_vals(
                row.get('total', 0.0),
                prev['products'].get(row['name'], 0.0)))

    def _attach_category_comparison(self, category_summary, prev):
        for row in category_summary['rows']:
            cur = float(row['total_fmt'].replace(',', ''))
            row.update(self._cmp_vals(
                cur, prev['categories'].get(row['name'], 0.0)))

    # --- القسم الجديد: تفاصيل جميع المنتجات المباعة حسب الفئة ------------
    def _products_detail(self, section4, prev):
        """جميع المنتجات المباعة (شاملة المتجر الإلكتروني) مقسمة على
        الفئات، مرتبة داخل كل فئة من الأعلى إلى الأقل، بنفس أعمدة قسم
        أعلى المنتجات + أعمدة المقارنة بالشهر السابق."""
        cats = []
        for cat in section4['categories']:
            prows = []
            for p in sorted(cat['products'],
                            key=lambda x: x.get('total', 0.0),
                            reverse=True):
                row = {
                    'name': p['name'],
                    'qty_fmt': p['qty_fmt'],
                    'avg_fmt': p['avg_fmt'],
                    'discount_fmt': p['discount_fmt'],
                    'total_fmt': p['total_fmt'],
                }
                row.update(self._cmp_vals(
                    p.get('total', 0.0),
                    prev['products'].get(p['name'], 0.0)))
                prows.append(row)
            crow = {
                'name': cat['name'],
                'product_count': len(prows),
                'qty_fmt': cat['qty_fmt'],
                'total': cat.get('total', 0.0),
                'total_fmt': cat['total_fmt'],
                'rows': prows,
            }
            crow.update(self._cmp_vals(
                cat.get('total', 0.0),
                prev['categories'].get(cat['name'], 0.0)))
            cats.append(crow)
        cats.sort(key=lambda c: c['total'], reverse=True)
        return {'categories': cats, 'count': len(cats)}

    # --- القسم الشهري: عملاء VIP (نقاط البيع فقط، فوق الحد) --------------
    def _monthly_vip(self, sales_orders, old_partner_ids, prev):
        """عملاء VIP الشهري: قنوات نقاط البيع فقط (بدون فواتير المتجر
        الإلكتروني التجميعية)، كل عميل تجاوز إنفاقه حد VIP_MIN_TOTAL،
        مع الفروع التي تمت فيها مبيعاته وأعمدة المقارنة بالشهر السابق."""
        per = {}
        for order in sales_orders:
            partner = order.partner_id
            if not partner:
                continue
            vals = per.setdefault(partner.id, {
                'partner_id': partner.id,
                'name': partner.name,
                'phone': partner.mobile or partner.phone or '-',
                'total': 0.0, 'count': 0, 'branches': set(),
            })
            vals['total'] += order.amount_total
            vals['count'] += 1
            vals['branches'].add(order.session_id.config_id.name)
        vips = sorted(
            (v for v in per.values() if v['total'] > self.VIP_MIN_TOTAL),
            key=lambda v: v['total'], reverse=True)
        rows = []
        for i, v in enumerate(vips, start=1):
            row = {
                'rank': i,
                'name': v['name'],
                'phone': v['phone'],
                'ptype': 'قديم' if v['partner_id'] in old_partner_ids
                         else 'جديد',
                'branches_fmt': '، '.join(sorted(v['branches'])),
                'count': v['count'],
                'avg_fmt': self._fmt_amount(
                    v['total'] / v['count'] if v['count'] else 0.0),
                'total_fmt': self._fmt_amount(v['total']),
            }
            row.update(self._cmp_vals(
                v['total'], prev['customers'].get(v['partner_id'], 0.0)))
            rows.append(row)
        return {
            'rows': rows,
            'total_customers': len(per),
            'threshold_fmt': self._fmt_amount(self.VIP_MIN_TOTAL),
        }

    # --- القسم الجديد: العملاء المشتركون في أكثر من قناة بيع -------------
    def _common_channel_customers(self, sales_orders, online,
                                  old_partner_ids, prev):
        """العملاء الذين اشتروا من قناتين أو أكثر خلال الشهر (شاملة قناة
        المتجر الإلكتروني). توحيد هوية العميل عبر القنوات يتم برقم
        الهاتف الموحّد (آخر 9 أرقام) حتى لو سُجل بأكثر من بطاقة عميل،
        مع نفس بيانات قسم VIP + القنوات المشتركة + المقارنة."""
        per = {}

        def add(partner_id, name, phone, is_new, amount, count, branch):
            key = self._phone_key(phone) or ('pid', partner_id)
            vals = per.setdefault(key, {
                'name': name,
                'phone': phone or '-',
                'total': 0.0, 'count': 0, 'branches': set(),
                'pids': set(), 'is_new': is_new,
                'phone_key': self._phone_key(phone),
            })
            vals['total'] += amount
            vals['count'] += count
            vals['branches'].add(branch)
            vals['pids'].add(partner_id)
            # «قديم» تغلب: يكفي أن يكون قديماً في قناة واحدة
            vals['is_new'] = vals['is_new'] and is_new

        for order in sales_orders:
            partner = order.partner_id
            if not partner:
                continue
            add(partner.id, partner.name,
                partner.mobile or partner.phone,
                partner.id not in old_partner_ids,
                order.amount_total, 1,
                order.session_id.config_id.name)
        if online:
            for pid, cv in online['customers'].items():
                add(pid, cv['name'], cv['phone'], cv['is_new'],
                    cv['total'], cv['count'], online['name'])

        shared = sorted(
            (v for v in per.values() if len(v['branches']) > 1),
            key=lambda v: v['total'], reverse=True)
        rows = []
        for i, v in enumerate(shared, start=1):
            # إنفاق الشهر السابق: برقم الهاتف الموحّد أولاً ثم بالمعرف
            prev_total = None
            if v['phone_key']:
                prev_total = prev['customers_by_phone'].get(v['phone_key'])
            if prev_total is None:
                prev_total = sum(prev['customers'].get(pid, 0.0)
                                 for pid in v['pids'])
            row = {
                'rank': i,
                'name': v['name'],
                'phone': v['phone'],
                'ptype': 'جديد' if v['is_new'] else 'قديم',
                'branches_fmt': '، '.join(sorted(v['branches'])),
                'count': v['count'],
                'avg_fmt': self._fmt_amount(
                    v['total'] / v['count'] if v['count'] else 0.0),
                'total_fmt': self._fmt_amount(v['total']),
            }
            row.update(self._cmp_vals(v['total'], prev_total))
            rows.append(row)
        return {'rows': rows, 'count': len(rows)}

    # =====================================================================
    # الأجزاء التفصيلية: بيانات كاملة (غير مقتطعة) لكل قناة على حدة
    # =====================================================================
    def _build_channels(self, data, sales_orders, refund_orders,
                        order_discounts, discount_product_ids,
                        old_partner_ids, online):
        channels = []
        for config in self.config_ids:
            ch_sales = sales_orders.filtered(
                lambda o, c=config: o.session_id.config_id == c)
            ch_refunds = refund_orders.filtered(
                lambda o, c=config: o.session_id.config_id == c)
            channels.append(self._pos_channel_dataset(
                config, ch_sales, ch_refunds, data, order_discounts,
                discount_product_ids, old_partner_ids))
        if online:
            channels.append(self._online_channel_dataset(online))
        return channels

    def _pos_channel_dataset(self, config, ch_sales, ch_refunds, data,
                             order_discounts, discount_product_ids,
                             old_partner_ids):
        name = config.name
        weeks = self._monthly_weekly_breakdown(
            ch_sales, ch_refunds, order_discounts)
        inv_rows = [r for r in data['section2']['rows']
                    if r.get('pos') == name]
        ref_rows = [r for r in data['section3']['rows']
                    if r.get('pos') == name]
        ref_rows = sorted(ref_rows,
                          key=lambda r: abs(r.get('total', 0.0)),
                          reverse=True)
        products = self._prepare_section_products(
            ch_sales, discount_product_ids)
        cat_summary = self._weekly_category_summary(products)
        customers = self._channel_customers(ch_sales, old_partner_ids)
        emp_cfg = next(
            (c for c in data['section5']['configs'] if c['name'] == name),
            {'rows': [], 'subtotal': {}})
        disc_cfg = next(
            (c for c in data['section6']['configs'] if c['name'] == name),
            None)
        gross = sum(o.amount_total for o in ch_sales)
        refunds = sum(abs(o.amount_total) for o in ch_refunds)
        net = gross - refunds
        count = len(ch_sales)
        partners = ch_sales.mapped('partner_id')
        return {
            'name': name,
            'kpis': {
                'gross_fmt': self._fmt_amount(gross),
                'refunds_fmt': self._fmt_amount(refunds),
                'net_fmt': self._fmt_amount(net),
                'invoices': count,
                'avg_fmt': self._fmt_amount(net / count if count else 0.0),
                'customers': len(partners),
                'discounts_fmt': self._fmt_amount(
                    sum(order_discounts.get(o.id, 0.0) for o in ch_sales)),
            },
            'weeks': weeks,
            'invoices': {'rows': inv_rows, 'count': len(inv_rows),
                         'total_fmt': self._fmt_amount(
                             sum(r.get('total', 0.0) for r in inv_rows))},
            'refunds': {'rows': ref_rows, 'count': len(ref_rows),
                        'total_fmt': self._fmt_amount(
                            -sum(abs(r.get('total', 0.0))
                                 for r in ref_rows))},
            'products': products,
            'category_summary': cat_summary,
            'customers': customers,
            'employees': emp_cfg,
            'discounts': disc_cfg,
        }

    def _channel_customers(self, ch_sales, old_partner_ids):
        per = {}
        for o in ch_sales:
            p = o.partner_id
            if not p:
                continue
            v = per.setdefault(p.id, {
                'name': p.name,
                'phone': p.mobile or p.phone or '-',
                'ptype': 'قديم' if p.id in old_partner_ids else 'جديد',
                'count': 0, 'total': 0.0,
            })
            v['count'] += 1
            v['total'] += o.amount_total
        rows = sorted(per.values(), key=lambda r: r['total'], reverse=True)
        out = []
        for i, r in enumerate(rows, 1):
            out.append({
                'rank': i, 'name': r['name'], 'phone': r['phone'],
                'ptype': r['ptype'], 'count': r['count'],
                'avg_fmt': self._fmt_amount(
                    r['total'] / r['count'] if r['count'] else 0.0),
                'total_fmt': self._fmt_amount(r['total']),
            })
        return {'rows': out, 'total_customers': len(out)}

    def _online_channel_dataset(self, online):
        cats_struct = {'categories': [], 'total_qty_fmt': '0',
                       'total_avg_fmt': self._fmt_amount(0),
                       'total_discount_fmt':
                       self._fmt_amount(online['discounts']),
                       'total_fmt': self._fmt_amount(0)}
        self._merge_online_products(cats_struct, online['cats'])
        cats_struct['total_discount_fmt'] = self._fmt_amount(
            sum(c.get('discount', 0.0) or
                float(c['discount_fmt'].replace(',', ''))
                for c in cats_struct['categories']) or online['discounts'])
        cat_summary = self._weekly_category_summary(cats_struct)
        weeks_rows = []
        best = 0.0
        for i, b in enumerate(online['week_buckets']):
            wnet = b['gross'] - b['refunds']
            best = max(best, wnet)
        t_net, t_cnt = 0.0, 0
        for i, b in enumerate(online['week_buckets']):
            ws, we = online['weeks'][i]
            wnet = b['gross'] - b['refunds']
            t_net += wnet
            t_cnt += b['count']
            weeks_rows.append({
                'label': 'أسبوع %d' % (i + 1),
                'range_fmt': '%s - %s' % (ws.strftime('%m-%d'),
                                          we.strftime('%m-%d')),
                'total_fmt': self._fmt_amount(wnet),
                'count': b['count'],
                'avg_fmt': self._fmt_amount(
                    wnet / b['count'] if b['count'] else 0.0),
                'discounts_fmt': self._fmt_amount(b['discounts']),
                'customers': len(b['partners']),
                'is_best': best > 0 and wnet == best,
            })
        cust_rows = []
        for i, cv in enumerate(sorted(online['customers'].values(),
                                      key=lambda c: c['total'],
                                      reverse=True), 1):
            cust_rows.append({
                'rank': i, 'name': cv['name'], 'phone': cv['phone'],
                'ptype': 'جديد' if cv['is_new'] else 'قديم',
                'count': cv['count'],
                'avg_fmt': self._fmt_amount(
                    cv['total'] / cv['count'] if cv['count'] else 0.0),
                'total_fmt': self._fmt_amount(cv['total']),
            })
        emp_rows = self._online_employee_rows(online)
        return {
            'name': online['name'],
            'kpis': {
                'gross_fmt': self._fmt_amount(online['gross']),
                'refunds_fmt': self._fmt_amount(online['refunds']),
                'net_fmt': self._fmt_amount(online['net']),
                'invoices': online['count'],
                'avg_fmt': self._fmt_amount(
                    online['net'] / online['count']
                    if online['count'] else 0.0),
                'customers': len(online['partners']),
                'discounts_fmt': self._fmt_amount(online['discounts']),
            },
            'weeks': {'rows': weeks_rows, 'total': {
                'total_fmt': self._fmt_amount(t_net), 'count': t_cnt,
                'avg_fmt': self._fmt_amount(
                    t_net / t_cnt if t_cnt else 0.0),
                'discounts_fmt': self._fmt_amount(online['discounts']),
                'customers': len(online['partners'])}},
            'invoices': {'rows': online['inv_rows'],
                         'count': len(online['inv_rows']),
                         'total_fmt': self._fmt_amount(online['gross'])},
            'refunds': {'rows': online['ref_rows'],
                        'count': len(online['ref_rows']),
                        'total_fmt':
                        self._fmt_amount(-online['refunds'])},
            'products': cats_struct,
            'category_summary': cat_summary,
            'customers': {'rows': cust_rows,
                          'total_customers': len(cust_rows)},
            'employees': {'name': online['name'], 'rows': emp_rows,
                          'subtotal':
                          self._employee_subtotal(emp_rows, online)},
            'discounts': ({
                'name': online['name'],
                'rows': [{
                    'name': 'خصومات بنود الفواتير',
                    'total_fmt': self._fmt_amount(online['discounts']),
                    'count': online['count'],
                    'avg_fmt': self._fmt_amount(
                        online['discounts'] / online['count']
                        if online['count'] else 0.0)}],
                'subtotal_fmt': self._fmt_amount(online['discounts']),
                'subtotal_count': online['count'],
                'subtotal_avg_fmt': self._fmt_amount(
                    online['discounts'] / online['count']
                    if online['count'] else 0.0),
            } if online['discounts'] else None),
        }

    # =====================================================================
    # الرسوم البيانية: أبعاد محسوبة بالبايثون (CSS خالص - آمن للسيرفر)
    # =====================================================================
    CHART_BAR_MAX_H = 78

    def _build_charts(self, data):
        def raw(fmt):
            try:
                return float(str(fmt).replace(',', ''))
            except (TypeError, ValueError):
                return 0.0
        # 1) أشرطة القنوات الأفقية (صافي)
        ch_rows = data['section1']['rows']
        mx = max((r.get('total', raw(r['total_fmt'])) for r in ch_rows),
                 default=0.0)
        palette = ['#1B4332', '#2D5443', '#C6A46C', '#8A9B8E']
        channels_chart = []
        for i, r in enumerate(ch_rows):
            v = r.get('total', raw(r['total_fmt']))
            channels_chart.append({
                'name': r['name'], 'value_fmt': self._fmt_amount(v),
                'share_fmt': r['share_fmt'],
                'width': '{:.1f}%'.format(v / mx * 100.0 if mx else 0.0),
                'color': palette[i % len(palette)],
            })
        # 2) أعمدة أسابيع الشهر (صافي)
        wk = data['weekly_rows']['rows']
        mxw = max((raw(r['total_fmt']) for r in wk), default=0.0)
        weeks_chart = [{
            'label': r['label'].replace('أسبوع ', 'أ'),
            'value_fmt': r['total_fmt'],
            'h': '{}px'.format(
                int(raw(r['total_fmt']) / mxw * self.CHART_BAR_MAX_H) + 3
                if mxw else 3),
            'is_best': r['is_best'],
        } for r in wk]
        # 3) أعمدة اتجاه الأشهر
        tr = data['trend']['rows']
        mxt = max((raw(r['total_fmt']) for r in tr), default=0.0)
        trend_chart = [{
            'label': r['label'].split(' ')[0],
            'value_fmt': r['total_fmt'],
            'h': '{}px'.format(
                int(raw(r['total_fmt']) / mxt * self.CHART_BAR_MAX_H) + 3
                if mxt else 3),
            'is_current': r['is_current'],
        } for r in tr]
        # 4) أشرطة أعلى الفئات
        cats = data['category_summary']['rows'][:8]
        mxc = max((raw(c['total_fmt']) for c in cats), default=0.0)
        cats_chart = [{
            'name': c['name'], 'value_fmt': c['total_fmt'],
            'share_fmt': c['share_fmt'],
            'width': '{:.1f}%'.format(
                raw(c['total_fmt']) / mxc * 100.0 if mxc else 0.0),
        } for c in cats]
        return {'channels': channels_chart, 'weeks': weeks_chart,
                'trend': trend_chart, 'categories': cats_chart}

    # =====================================================================
    # توليد التقرير: ملخص المبيعات الشهري فقط (بدون صفحة المحتوى وبدون
    # أجزاء تفاصيل المبيعات لكل قناة)، مع ختم ترقيم الصفحات N / M
    # =====================================================================
    def action_print_report(self):
        self.ensure_one()
        self._apply_month()
        data = self.prepare_monthly_report_data()
        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
            'akshab_pos_sales_report.action_report_pos_monthly',
            res_ids=self.ids, data={'monthly_data': data})

        from ..report.pos_monthly_report import merge_and_stamp
        merged = merge_and_stamp([pdf])
        filename = self.get_print_report_name() + '.pdf'
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'raw': merged,
            'mimetype': 'application/pdf',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }
