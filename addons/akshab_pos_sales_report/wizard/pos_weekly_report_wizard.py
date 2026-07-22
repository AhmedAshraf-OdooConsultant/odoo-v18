# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class AkshabPosWeeklyReportWizard(models.TransientModel):
    """التقرير الأسبوعي: يرث محرك حسابات التقرير اليومي كاملاً (وراثة نموذج
    أولي داخل الأدون نفسه - لا مساس بأي نموذج أساسي) ويضيف الأقسام
    التحليلية الأسبوعية."""
    _name = 'akshab.pos.weekly.report.wizard'
    _inherit = 'akshab.pos.sales.report.wizard'
    _description = 'معالج تقرير المبيعات الأسبوعي - أخشاب البخور'

    def _default_week_start(self):
        """السبت الماضي لآخر أسبوع مكتمل (أسبوع التجزئة: السبت - الجمعة)."""
        today = fields.Date.context_today(self)
        current_saturday = today - timedelta(days=(today.weekday() - 5) % 7)
        return current_saturday - timedelta(days=7)

    week_start = fields.Date(
        string='بداية الأسبوع (السبت)', required=True,
        default=_default_week_start)

    def _apply_week(self):
        """تحويل تاريخ بداية الأسبوع إلى فترة 7 أيام كاملة بتوقيت المستخدم."""
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        for wizard in self:
            if not wizard.week_start:
                continue
            start_local = tz.localize(
                datetime.combine(wizard.week_start, time.min))
            end_local = start_local + timedelta(days=7)
            wizard.date_from = start_local.astimezone(
                pytz.utc).replace(tzinfo=None)
            wizard.date_to = end_local.astimezone(
                pytz.utc).replace(tzinfo=None) - timedelta(seconds=1)

    @api.onchange('week_start')
    def _onchange_week_start(self):
        self._apply_week()

    def action_print_report(self):
        self.ensure_one()
        self._apply_week()
        return self.env.ref(
            'akshab_pos_sales_report.action_report_pos_weekly'
        ).report_action(self)

    def get_print_report_name(self):
        self.ensure_one()
        end = self.week_start + timedelta(days=6)
        return 'تقرير المبيعات الأسبوعي - من %s إلى %s' % (
            self.week_start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))

    # ------------------------------------------------------------------
    # بيانات التقرير الأسبوعي
    # ------------------------------------------------------------------
    def prepare_weekly_report_data(self):
        self.ensure_one()
        self._apply_week()
        # المحرك اليومي كاملاً: KPIs + الأقسام الستة بكل منطقها الموحد
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

        week_end = self.week_start + timedelta(days=6)
        data['week_from'] = '%s %s' % (
            self.ARABIC_DAYS[self.week_start.weekday()],
            self.week_start.strftime('%Y-%m-%d'))
        data['week_to'] = '%s %s' % (
            self.ARABIC_DAYS[week_end.weekday()],
            week_end.strftime('%Y-%m-%d'))

        data['daily'] = self._weekly_daily_breakdown(
            sales_orders, refund_orders, order_discounts)
        data['matrix'] = self._weekly_matrix(sales_orders, refund_orders)
        data['top_invoices'] = {
            'rows': data['section2']['rows'][:10],
            'count': data['section2']['count'],
            'total_fmt': data['section2']['total_fmt'],
        }
        data['top_products'] = self._weekly_top_products(data['section4'])
        data['category_summary'] = self._weekly_category_summary(
            data['section4'])
        data['comparison'], data['trend'] = \
            self._weekly_trend_and_comparison(data, discount_product_ids)
        vip_partners = sales_orders.mapped('partner_id')
        data['vip'] = self._weekly_vip(
            sales_orders, self._get_old_partner_ids(vip_partners))
        return data

    def _local_date(self, dt):
        return fields.Datetime.context_timestamp(self, dt).date()

    # --- القسم الأسبوعي 1: المبيعات اليومية -----------------------------
    def _weekly_daily_breakdown(self, sales_orders, refund_orders,
                                order_discounts):
        days = {}
        for i in range(7):
            d = self.week_start + timedelta(days=i)
            days[d] = {
                'day_name': self.ARABIC_DAYS[d.weekday()],
                'date_fmt': d.strftime('%Y-%m-%d'),
                'total': 0.0, 'count': 0,
                'discounts': 0.0, 'partners': set(), 'refunds': 0.0,
            }
        for order in sales_orders:
            d = self._local_date(order.date_order)
            if d not in days:
                continue
            vals = days[d]
            vals['total'] += order.amount_total
            vals['count'] += 1
            vals['discounts'] += order_discounts.get(order.id, 0.0)
            if order.partner_id:
                vals['partners'].add(order.partner_id.id)
        for order in refund_orders:
            d = self._local_date(order.date_order)
            if d in days:
                days[d]['refunds'] += abs(order.amount_total)
        # الصافي اليومي = مبيعات اليوم - مرتجعاته
        for vals in days.values():
            vals['net'] = vals['total'] - vals['refunds']

        best_total = max((v['net'] for v in days.values()), default=0.0)
        rows = []
        for d in sorted(days):
            vals = days[d]
            rows.append({
                'day_name': vals['day_name'],
                'date_fmt': vals['date_fmt'],
                'total_fmt': self._fmt_amount(vals['net']),
                'count': vals['count'],
                'avg_fmt': self._fmt_amount(
                    vals['net'] / vals['count'] if vals['count'] else 0.0),
                'discounts_fmt': self._fmt_amount(vals['discounts']),
                'customers': len(vals['partners']),
                'is_best': best_total > 0 and vals['net'] == best_total,
            })
        t_total = sum(v['net'] for v in days.values())
        t_count = sum(v['count'] for v in days.values())
        all_partners = set()
        for v in days.values():
            all_partners |= v['partners']
        return {
            'rows': rows,
            'total': {
                'total_fmt': self._fmt_amount(t_total),
                'count': t_count,
                'avg_fmt': self._fmt_amount(
                    t_total / t_count if t_count else 0.0),
                'discounts_fmt': self._fmt_amount(
                    sum(v['discounts'] for v in days.values())),
                'customers': len(all_partners),
            },
        }

    # --- القسم الأسبوعي 3: مصفوفة الفروع × الأيام -----------------------
    def _weekly_matrix(self, sales_orders, refund_orders):
        day_dates = [self.week_start + timedelta(days=i) for i in range(7)]
        headers = [
            {'day_name': self.ARABIC_DAYS[d.weekday()],
             'date_fmt': d.strftime('%m-%d')}
            for d in day_dates
        ]
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'days': {d: 0.0 for d in day_dates},
                'total': 0.0,
            })
            d = self._local_date(order.date_order)
            if d in vals['days']:
                vals['days'][d] += order.amount_total
                vals['total'] += order.amount_total
        # خصم المرتجعات من خلية فرعها/يومها: الخلايا = صافي
        for order in refund_orders:
            cfg = order.session_id.config_id
            vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'days': {d: 0.0 for d in day_dates},
                'total': 0.0,
            })
            d = self._local_date(order.date_order)
            if d in vals['days']:
                vals['days'][d] -= abs(order.amount_total)
                vals['total'] -= abs(order.amount_total)
        rows = []
        for vals in per_config.values():
            rows.append({
                'name': vals['name'],
                'cells': [self._fmt_amount(vals['days'][d])
                          for d in day_dates],
                'total_fmt': self._fmt_amount(vals['total']),
                'total': vals['total'],
            })
        rows.sort(key=lambda r: r['total'], reverse=True)
        day_totals = [
            self._fmt_amount(sum(v['days'][d] for v in per_config.values()))
            for d in day_dates
        ]
        grand = sum(v['total'] for v in per_config.values())
        return {
            'headers': headers,
            'rows': rows,
            'day_totals': day_totals,
            'grand_fmt': self._fmt_amount(grand),
        }

    # --- القسم الأسبوعي 7: أعلى المنتجات مبيعاً --------------------------
    TOP_PRODUCTS_LIMIT = 15

    def _weekly_top_products(self, section4):
        flat = []
        for cat in section4['categories']:
            for p in cat['products']:
                flat.append({
                    'name': p['name'],
                    'category': cat['name'],
                    'qty_fmt': p['qty_fmt'],
                    'avg_fmt': p['avg_fmt'],
                    'discount_fmt': p['discount_fmt'],
                    'total': p['total'],
                    'total_fmt': p['total_fmt'],
                })
        flat.sort(key=lambda p: p['total'], reverse=True)
        rows = flat[:self.TOP_PRODUCTS_LIMIT]
        for i, row in enumerate(rows, start=1):
            row['rank'] = i
        return {'rows': rows, 'total_count': len(flat)}

    # --- القسم الأسبوعي 8: ملخص الفئات -----------------------------------
    def _weekly_category_summary(self, section4):
        grand = sum(c['total'] for c in section4['categories'])
        rows = []
        for cat in section4['categories']:
            rows.append({
                'name': cat['name'],
                'qty_fmt': cat['qty_fmt'],
                'avg_fmt': cat['avg_fmt'],
                'discount_fmt': cat['discount_fmt'],
                'total_fmt': cat['total_fmt'],
                'share_fmt': '%{:.1f}'.format(
                    cat['total'] / grand * 100.0 if grand else 0.0),
            })
        return {
            'rows': rows,
            'count': len(rows),
            'total_qty_fmt': section4['total_qty_fmt'],
            'total_avg_fmt': section4['total_avg_fmt'],
            'total_discount_fmt': section4['total_discount_fmt'],
            'total_fmt': section4['total_fmt'],
        }

    # --- القسم الأسبوعي 9: عملاء VIP -------------------------------------
    VIP_LIMIT = 10

    def _weekly_vip(self, sales_orders, old_partner_ids):
        """أعلى العملاء إنفاقاً خلال الأسبوع (يُستبعد البيع النقدي بلا عميل)."""
        per_partner = {}
        for order in sales_orders:
            partner = order.partner_id
            if not partner:
                continue
            vals = per_partner.setdefault(partner.id, {
                'partner_id': partner.id,
                'name': partner.name,
                'phone': partner.mobile or partner.phone or '-',
                'total': 0.0, 'count': 0,
            })
            vals['total'] += order.amount_total
            vals['count'] += 1
        top = sorted(per_partner.values(),
                     key=lambda v: v['total'], reverse=True)[:self.VIP_LIMIT]
        rows = []
        for i, vals in enumerate(top, start=1):
            rows.append({
                'rank': i,
                'name': vals['name'],
                'phone': vals['phone'],
                'ptype': 'قديم' if vals['partner_id'] in old_partner_ids
                         else 'جديد',
                'count': vals['count'],
                'avg_fmt': self._fmt_amount(
                    vals['total'] / vals['count'] if vals['count'] else 0.0),
                'total_fmt': self._fmt_amount(vals['total']),
            })
        return {'rows': rows, 'total_customers': len(per_partner)}

    # --- الاتجاه الأسبوعي والمقارنة (استعلام واحد لثلاثة أسابيع سابقة) ---
    TREND_WEEKS_BACK = 3

    def _weekly_trend_and_comparison(self, data, discount_product_ids):
        """يجلب طلبات الأسابيع الثلاثة السابقة باستعلام واحد ويبني منها
        جدول اتجاه آخر 4 أسابيع وقسم المقارنة بالأسبوع السابق معاً."""
        back = self.TREND_WEEKS_BACK
        window_from = self.date_from - timedelta(days=7 * back)
        prev_orders = self.env['pos.order'].search([
            ('date_order', '>=', window_from),
            ('date_order', '<', self.date_from),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', self.config_ids.ids),
        ])
        buckets = [
            {'gross': 0.0, 'refunds': 0.0, 'count': 0,
             'partners': set(), 'discounts': 0.0}
            for _i in range(back)
        ]
        week_seconds = 7 * 24 * 3600
        for order in prev_orders:
            idx = int((order.date_order - window_from).total_seconds()
                      // week_seconds)
            idx = min(max(idx, 0), back - 1)
            b = buckets[idx]
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

        # ---------- جدول الاتجاه: 3 أسابيع سابقة + الأسبوع الحالي ----------
        # grand_total أصبح صافياً؛ الإجمالي قبل المرتجعات = الصافي + المرتجعات
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
        trend_rows = []
        prev_net = None
        for i in range(back + 1):
            if i < back:
                b = buckets[i]
                net = b['gross'] - b['refunds']
                count = b['count']
                customers, discounts = len(b['partners']), b['discounts']
            else:
                net, count = cur['net'], cur['count']
                customers, discounts = cur['customers'], cur['discounts']
            w_start = self.week_start - timedelta(days=7 * (back - i))
            w_end = w_start + timedelta(days=6)
            if prev_net:
                diff_pct = (net - prev_net) / prev_net * 100.0
                growth_fmt = '%{:+.1f}'.format(diff_pct)
                growth_class = ('ak-up' if diff_pct > 0
                                else 'ak-down' if diff_pct < 0 else 'ak-flat')
            else:
                growth_fmt, growth_class = '—', 'ak-flat'
            trend_rows.append({
                'label': 'من %s إلى %s' % (
                    w_start.strftime('%Y-%m-%d'), w_end.strftime('%Y-%m-%d')),
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

        # ---------- المقارنة بالأسبوع السابق (الحزمة الأخيرة) ----------
        pb = buckets[-1]
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
        comparison = {'rows': rows}
        return comparison, trend
