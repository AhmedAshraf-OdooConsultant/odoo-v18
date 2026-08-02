# -*- coding: utf-8 -*-
"""تقرير المبيعات للفترة: نفس محتوى التقرير الشهري بالكامل لكن لفترة
حرة (حتى سنة) - مثل 7 أشهر من 2026 مقارنة بنفس الفترة من 2025، أو ربع
سنة - مع مواكبة كل الأقسام والعناوين للفترة المختارة، وقناة B2B
الاختيارية التي تظهر في مقارنة مبيعات القنوات فقط."""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

PERIOD_MAX_DAYS = 366


class AkshabPosPeriodReportWizard(models.TransientModel):
    _name = 'akshab.pos.period.report.wizard'
    _inherit = 'akshab.pos.monthly.report.wizard'
    _description = 'معالج تقرير المبيعات للفترة - أخشاب البخور'

    TREND_PERIODS = 4

    def _default_period_start(self):
        today = fields.Date.context_today(self)
        return today.replace(month=1, day=1)

    def _default_period_end(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1) - timedelta(days=1)

    period_start = fields.Date(
        string='من تاريخ', required=True, default=_default_period_start)
    period_end = fields.Date(
        string='إلى تاريخ', required=True, default=_default_period_end)
    comparison_mode = fields.Selection(
        [('year_ago', 'نفس الفترة من العام السابق'),
         ('previous', 'الفترة السابقة مباشرة')],
        string='فترة المقارنة', required=True, default='year_ago')

    # إعادة تعريف حقول فواتير الأونلاين بجداول علاقات خاصة بهذا المعالج
    # (جداول العلاقات المسماة في الشهري لا يمكن مشاركتها بين نموذجين)
    online_move_prev_ids = fields.Many2many(
        'account.move', relation='akshab_pos_period_wiz_prev_move_rel',
        string='فواتير المتجر الإلكتروني (فترة المقارنة)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير قناة Online Store لفترة المقارنة - تُستخدم '
             'في أعمدة «الفترة السابقة / التغير / نسبة التغير»')
    online_move_m2_ids = fields.Many2many(
        'account.move', relation='akshab_pos_period_wiz_m2_move_rel',
        string='فواتير المتجر الإلكتروني (الفترة الثالثة)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير الأونلاين للفترة الثالثة في قسم الاتجاه')
    online_move_m3_ids = fields.Many2many(
        'account.move', relation='akshab_pos_period_wiz_m3_move_rel',
        string='فواتير المتجر الإلكتروني (الفترة الرابعة)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير الأونلاين للفترة الرابعة في قسم الاتجاه')

    # قناة B2B: فواتير تجميعية مثل الأونلاين، تظهر في مقارنة مبيعات
    # القنوات فقط (قد يكون لها مبيعات في فترة المقارنة دون فترة التقرير)
    B2B_CHANNEL_NAME = 'B2B'
    b2b_move_ids = fields.Many2many(
        'account.move', relation='akshab_pos_period_wiz_b2b_rel',
        string='فواتير قناة B2B (فترة التقرير)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير قناة B2B لفترة التقرير - تظهر في قسم '
             'مقارنة مبيعات قنوات البيع فقط')
    b2b_move_prev_ids = fields.Many2many(
        'account.move', relation='akshab_pos_period_wiz_b2b_prev_rel',
        string='فواتير قناة B2B (فترة المقارنة)',
        domain=[('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted')],
        help='اختياري: فواتير قناة B2B لفترة المقارنة')

    # ------------------------------------------------------------------
    # الفترة وحدودها
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """تقرير الفترة يسمح حتى سنة كاملة (يتجاوز حد الـ92 يوماً)."""
        for wizard in self:
            if wizard.date_to <= wizard.date_from:
                raise ValidationError(
                    'تاريخ النهاية يجب أن يكون بعد تاريخ البداية.')
            if (wizard.date_to - wizard.date_from).days > PERIOD_MAX_DAYS:
                raise ValidationError(
                    'أقصى فترة لتقرير الفترة هي سنة كاملة (%s يوماً).'
                    % PERIOD_MAX_DAYS)

    def _apply_month(self):
        """تطبيع حدود الفترة المختارة بتوقيت المستخدم (كتابة ذرّية)."""
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        for wizard in self:
            if not wizard.period_start or not wizard.period_end:
                continue
            start_local = tz.localize(datetime.combine(
                wizard.period_start, time.min))
            end_local = tz.localize(datetime.combine(
                wizard.period_end + timedelta(days=1), time.min))
            vals = {
                'month_start': wizard.period_start,
                'date_from': start_local.astimezone(
                    pytz.utc).replace(tzinfo=None),
                'date_to': end_local.astimezone(
                    pytz.utc).replace(tzinfo=None) - timedelta(seconds=1),
            }
            if isinstance(wizard.id, models.NewId) or not wizard.id:
                wizard.update(vals)
            else:
                wizard.write(vals)

    @api.onchange('period_start', 'period_end')
    def _onchange_period(self):
        self._apply_month()

    def _period_first_day(self):
        return self.period_start or self.month_start

    def _month_last_day(self):
        return self.period_end

    def _period_days(self):
        return (self._month_last_day() - self._period_first_day()).days + 1

    @staticmethod
    def _shift_years(d, years):
        """إزاحة تاريخ بعدد سنوات مع معالجة 29 فبراير."""
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            return d.replace(year=d.year + years, month=2, day=28)

    def _period_range_back(self, steps):
        """حدود الفترة رقم steps للخلف (0 = فترة التقرير) بحسب نمط
        المقارنة: سنوات كاملة للخلف أو فترات متتالية بنفس الطول."""
        start, end = self._period_first_day(), self._month_last_day()
        if steps == 0:
            return start, end
        if self.comparison_mode == 'year_ago':
            return (self._shift_years(start, -steps),
                    self._shift_years(end, -steps))
        length = (end - start).days
        for _i in range(steps):
            end = start - timedelta(days=1)
            start = end - timedelta(days=length)
        return start, end

    def _bounds_utc(self, d_start, d_end):
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        d_from = tz.localize(datetime.combine(
            d_start, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        d_to = tz.localize(datetime.combine(
            d_end + timedelta(days=1), time.min)).astimezone(
            pytz.utc).replace(tzinfo=None) - timedelta(seconds=1)
        return d_from, d_to

    def _prev_period_bounds(self):
        """فترة المقارنة: نفس الفترة من العام السابق أو السابقة مباشرة."""
        p_start, p_end = self._period_range_back(1)
        return self._bounds_utc(p_start, p_end)

    # ------------------------------------------------------------------
    # التسميات والدلاء الزمنية
    # ------------------------------------------------------------------
    def _months_aligned(self):
        """هل الفترة محاذاة لأشهر ميلادية كاملة؟"""
        start, end = self._period_first_day(), self._month_last_day()
        next_day = end + timedelta(days=1)
        return start.day == 1 and next_day.day == 1

    def _range_label(self, start, end):
        next_day = end + timedelta(days=1)
        if start.day == 1 and next_day.day == 1:
            if start.year == end.year:
                if start.month == end.month:
                    return '%s %s' % (
                        self.ARABIC_MONTHS[start.month - 1], start.year)
                return '%s - %s %s' % (
                    self.ARABIC_MONTHS[start.month - 1],
                    self.ARABIC_MONTHS[end.month - 1], start.year)
            return '%s %s - %s %s' % (
                self.ARABIC_MONTHS[start.month - 1], start.year,
                self.ARABIC_MONTHS[end.month - 1], end.year)
        return 'من %s إلى %s' % (start.strftime('%Y-%m-%d'),
                                 end.strftime('%Y-%m-%d'))

    def _period_label(self):
        return self._range_label(
            self._period_first_day(), self._month_last_day())

    def get_print_report_name(self):
        self.ensure_one()
        return 'تقرير المبيعات للفترة - %s' % self._period_label()

    def _monthly_buckets(self):
        return self._period_days() > 35

    def _labels(self):
        labels = dict(self.REPORT_LABELS)
        prev_word = ('نفس الفترة من العام السابق'
                     if self.comparison_mode == 'year_ago'
                     else 'الفترة السابقة')
        bucket = 'شهر' if self._monthly_buckets() else 'أسبوع'
        labels.update({
            'report_title': 'تقرير المبيعات للفترة',
            'report_subtitle': 'PERIOD SALES REPORT',
            'cur': 'هذه الفترة',
            'prev': prev_word,
            'during': 'خلال الفترة',
            'vs_prev': 'مقارنة بـ%s' % prev_word,
            'period_row': 'الفترة',
            'total_cur': 'إجمالي الفترة',
            'summary_title': 'الملخص التنفيذي — أبرز نتائج الفترة',
            'cmp_title': 'مقارنة بـ%s' % prev_word,
            'ch_cmp_title': 'مقارنة مبيعات قنوات البيع بـ%s — صافي '
                            'المبيعات' % prev_word,
            'exec_title': 'مقارنة أداء قنوات البيع بـ%s — الفئات '
                          'والمنتجات' % prev_word,
            'trend_title': 'اتجاه آخر %d فترات مماثلة (جميع القنوات)'
                           % self.TREND_PERIODS,
            'trend_chart_title': 'اتجاه صافي المبيعات - آخر %d فترات '
                                 'مماثلة (جميع القنوات)'
                                 % self.TREND_PERIODS,
            'trend_col': 'الفترة',
            'matrix_title': 'صافي المبيعات ال%sية حسب قناة البيع'
                            % ('شهر' if self._monthly_buckets()
                               else 'أسبوع'),
            'best_bucket': 'أفضل %s في الفترة' % bucket,
            'growth_hl': 'نمو صافي المبيعات (%s)' % prev_word,
            'top_inv_title': 'أعلى 10 فواتير في الفترة (قنوات نقاط '
                             'البيع)',
            'inv_total': 'إجمالي فواتير الفترة (جميع القنوات)',
            'top_products_title': 'أعلى 30 منتجاً مبيعاً خلال الفترة '
                                  '(جميع القنوات)',
            'products_total': 'إجمالي المنتجات المباعة خلال الفترة',
            'vip_title': 'عملاء VIP — الأعلى إنفاقاً خلال الفترة لكل '
                         'قناة بيع',
            'vip_total': 'إجمالي عملاء الفترة المسجلين (قنوات نقاط '
                         'البيع)',
            'online_note': 'لمقارنة قناة Online Store: اختر فواتير '
                           'المتجر الإلكتروني لفترة المقارنة في معالج '
                           'التقرير.',
        })
        return labels

    def _month_weeks(self):
        """دلاء الفترة: أسابيع (7 أيام مع دمج الذيل) للفترات القصيرة،
        وأشهر ميلادية مقصوصة على حدود الفترة للفترات الطويلة."""
        first = self._period_first_day()
        last = self._month_last_day()
        buckets, cur = [], first
        if not self._monthly_buckets():
            while cur <= last:
                remaining = (last - cur).days + 1
                if remaining < 14:
                    buckets.append((cur, last))
                    break
                week_end = cur + timedelta(days=6)
                buckets.append((cur, week_end))
                cur = week_end + timedelta(days=1)
            return buckets
        while cur <= last and len(buckets) < 13:
            month_end = self._next_month_first(cur) - timedelta(days=1)
            b_end = min(month_end, last)
            buckets.append((cur, b_end))
            cur = b_end + timedelta(days=1)
        return buckets

    def _bucket_title(self, index, b_from, b_to):
        if self._monthly_buckets():
            return 'شهر %s %s' % (
                self.ARABIC_MONTHS[b_from.month - 1], b_from.year)
        return 'الأسبوع %d: من %s إلى %s' % (
            index, b_from.strftime('%Y-%m-%d'), b_to.strftime('%Y-%m-%d'))

    def _bucket_header(self, index, b_from, b_to):
        if self._monthly_buckets():
            return {'title': '%s %s' % (
                self.ARABIC_MONTHS[b_from.month - 1], b_from.year),
                'range_fmt': '%s - %s' % (b_from.strftime('%m-%d'),
                                          b_to.strftime('%m-%d'))}
        return {'title': 'أسبوع %d' % index,
                'range_fmt': '%s - %s' % (b_from.strftime('%m-%d'),
                                          b_to.strftime('%m-%d'))}

    # ------------------------------------------------------------------
    # قناة B2B: مقارنة مبيعات القنوات فقط
    # ------------------------------------------------------------------
    @staticmethod
    def _moves_net(moves):
        total = 0.0
        for m in moves.filtered(
                lambda x: x.state == 'posted'
                and x.move_type in ('out_invoice', 'out_refund')):
            sign = 1.0 if m.move_type == 'out_invoice' else -1.0
            total += sign * m.amount_total
        return total

    def _extra_channel_nets(self):
        if not self.b2b_move_ids and not self.b2b_move_prev_ids:
            return []
        return [{
            'name': self.B2B_CHANNEL_NAME,
            'cur': self._moves_net(self.b2b_move_ids),
            'prev': self._moves_net(self.b2b_move_prev_ids),
        }]

    # ------------------------------------------------------------------
    # الاتجاه: حتى 4 فترات مماثلة (نسخة خفيفة على قاعدة البيانات)
    # ------------------------------------------------------------------
    def _monthly_trend_and_comparison(self, data, discount_product_ids):
        online_fields = [None, self.online_move_prev_ids,
                         self.online_move_m2_ids, self.online_move_m3_ids]
        periods = []
        for step in range(self.TREND_PERIODS - 1, -1, -1):
            p_start, p_end = self._period_range_back(step)
            periods.append((step, p_start, p_end))

        rows, prev_net = [], None
        for step, p_start, p_end in periods:
            if step == 0:
                net = data['section1']['grand_total']
                count = data['section1']['total']['count']
                customers = data['section1']['total']['customers']
                discounts_fmt = self._fmt_amount(
                    data['section6']['grand_total'])
            else:
                d_from, d_to = self._bounds_utc(p_start, p_end)
                recs = self.env['pos.order'].search_read(
                    [('date_order', '>=', d_from),
                     ('date_order', '<=', d_to),
                     ('state', 'in', ('paid', 'done', 'invoiced')),
                     ('session_id.config_id', 'in', self.config_ids.ids)],
                    ['amount_total', 'partner_id'])
                net, count, partners = 0.0, 0, set()
                for r in recs:
                    net += r['amount_total']
                    if r['amount_total'] >= 0:
                        count += 1
                        if r['partner_id']:
                            partners.add(r['partner_id'][0])
                customers = len(partners)
                moves = online_fields[step] if step < len(
                    online_fields) else None
                if moves:
                    posted = moves.filtered(
                        lambda m: m.state == 'posted'
                        and m.move_type in ('out_invoice', 'out_refund'))
                    for m in posted:
                        if m.move_type == 'out_refund':
                            net -= m.amount_total
                        else:
                            net += m.amount_total
                            count += 1
                discounts_fmt = '—'
            if prev_net:
                diff_pct = (net - prev_net) / prev_net * 100.0
                growth_fmt = '%{:+.1f}'.format(diff_pct)
                growth_class = ('ak-up' if diff_pct > 0
                                else 'ak-down' if diff_pct < 0
                                else 'ak-flat')
            else:
                growth_fmt, growth_class = '—', 'ak-flat'
            rows.append({
                'label': self._range_label(p_start, p_end),
                'chart_label': (str(p_start.year)
                                if self.comparison_mode == 'year_ago'
                                else 'ف%d' % (self.TREND_PERIODS - step)),
                'total_fmt': self._fmt_amount(net),
                'count': count,
                'avg_fmt': self._fmt_amount(net / count if count else 0.0),
                'customers': customers,
                'discounts_fmt': discounts_fmt,
                'growth_fmt': growth_fmt,
                'growth_class': growth_class,
                'is_current': step == 0,
            })
            prev_net = net
        return {}, {'rows': rows}

    # ------------------------------------------------------------------
    # الطباعة
    # ------------------------------------------------------------------
    def action_print_report(self):
        self.ensure_one()
        self._apply_month()
        data = self.prepare_monthly_report_data()
        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
            'akshab_pos_sales_report.action_report_pos_period',
            res_ids=self.ids, data={'monthly_data': data})

        from ..report.pos_monthly_report import merge_and_stamp
        merged = merge_and_stamp([pdf])
        filename = self.get_print_report_name() + '.pdf'
        Attachment = self.env['ir.attachment']
        Attachment.search([
            ('name', '=', filename),
            ('res_model', '=', self._name),
        ]).unlink()
        attachment = Attachment.create({
            'name': filename,
            'type': 'binary',
            'raw': merged,
            'mimetype': 'application/pdf',
            'res_model': self._name,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }
