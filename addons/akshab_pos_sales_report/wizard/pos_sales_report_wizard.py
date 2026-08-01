# -*- coding: utf-8 -*-
import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# أقصى فترة مسموح بها للتقرير (حماية أداء السيرفر من الفترات الضخمة بالخطأ)
MAX_PERIOD_DAYS = 92

GENERAL_DISCOUNT = 'خصومات عامة'


class AkshabPosSalesReportWizard(models.TransientModel):
    _name = 'akshab.pos.sales.report.wizard'
    _description = 'معالج تقرير مبيعات التجزئة - أخشاب البخور'

    def _default_date_from(self):
        """بداية اليوم الحالي بتوقيت المستخدم."""
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(pytz.utc).replace(tzinfo=None)

    date_from = fields.Datetime(
        string='من تاريخ', required=True, default=_default_date_from)
    date_to = fields.Datetime(
        string='إلى تاريخ', required=True, default=fields.Datetime.now)
    config_ids = fields.Many2many(
        'pos.config', string='الفروع', required=True,
        default=lambda self: self.env['pos.config'].search([]))

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_to <= wizard.date_from:
                raise ValidationError(
                    'تاريخ النهاية يجب أن يكون بعد تاريخ البداية.')
            if (wizard.date_to - wizard.date_from).days > MAX_PERIOD_DAYS:
                raise ValidationError(
                    'أقصى فترة مسموح بها للتقرير هي %s يوماً '
                    'حفاظاً على أداء السيرفر. '
                    'للفترات الأطول يرجى تقسيم التقرير.' % MAX_PERIOD_DAYS)

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref(
            'akshab_pos_sales_report.action_report_pos_sales'
        ).report_action(self)

    # ------------------------------------------------------------------
    # اليوم واسم ملف الطباعة
    # ------------------------------------------------------------------
    ARABIC_DAYS = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس',
                   'الجمعة', 'السبت', 'الأحد']  # weekday(): 0 = الاثنين

    def _is_short_period(self):
        """الفترة أقل من 48 ساعة → تقرير يومي يحمل اسم اليوم."""
        self.ensure_one()
        return (self.date_to - self.date_from).total_seconds() < 48 * 3600

    def _get_day_parts(self):
        """اسم يوم بداية الفترة وتاريخه بتوقيت المستخدم."""
        local = fields.Datetime.context_timestamp(self, self.date_from)
        return self.ARABIC_DAYS[local.weekday()], local.strftime('%Y-%m-%d')

    def get_print_report_name(self):
        """اسم ملف الـ PDF: يتضمن اليوم فقط إذا كانت الفترة أقل من 48 ساعة."""
        self.ensure_one()
        if self._is_short_period():
            day_name, day_date = self._get_day_parts()
            return 'تقرير مبيعات التجزئة - يوم %s %s' % (day_name, day_date)
        return 'تقرير مبيعات التجزئة'

    # ------------------------------------------------------------------
    # أدوات مساعدة
    # ------------------------------------------------------------------
    @api.model
    def _fmt_amount(self, amount):
        return '{:,.2f}'.format(amount or 0.0)

    @api.model
    def _fmt_qty(self, qty):
        qty = qty or 0.0
        if float(qty).is_integer():
            return '{:,.0f}'.format(qty)
        return '{:,.2f}'.format(qty)

    def _fmt_dt(self, dt):
        if not dt:
            return '-'
        return fields.Datetime.context_timestamp(self, dt).strftime('%Y-%m-%d %H:%M')

    def _get_orders(self):
        """جميع طلبات نقاط البيع ضمن الفترة والفروع المحددة."""
        return self.env['pos.order'].search([
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', self.config_ids.ids),
        ])

    def _get_global_discount_product_ids(self):
        """منتجات الخصم العام (Global Discounts) المعرفة في إعدادات نقاط البيع.

        ميزة Global Discounts القياسية (وحدة pos_discount) تُنزل الخصم كبند
        منتج سالب في الطلب؛ نجمع كل منتجات الخصم المعرفة في جميع الفروع
        حتى نستبعدها من مبيعات المنتجات ونصنفها ضمن «خصومات عامة».
        """
        Config = self.env['pos.config']
        if 'discount_product_id' not in Config._fields:
            return set()
        configs = Config.search([])
        return set(configs.mapped('discount_product_id').ids)

    def _iter_order_discounts(self, order, discount_product_ids):
        """توليد أزواج (اسم الخصم، القيمة) لكل خصومات الطلب الواحد.

        المنطق الموحد المستخدم في الأقسام 1 و 5 و 6:
          1. بنود مكافآت برامج الخصم (الولاء/العروض/الأكواد) → باسم البرنامج
          2. بنود الخصم العام Global Discount → «خصومات عامة»
          3. نسبة الخصم اليدوية على البند → «خصومات عامة»
        """
        for line in order.lines:
            if 'reward_id' in line._fields and line.reward_id \
                    and line.price_subtotal_incl < 0:
                program = line.reward_id.program_id
                name = program.name or line.reward_id.description \
                    or 'برنامج خصم'
                yield name, abs(line.price_subtotal_incl)
            elif line.product_id.id in discount_product_ids \
                    and line.price_subtotal_incl < 0:
                yield GENERAL_DISCOUNT, abs(line.price_subtotal_incl)
            elif line.discount:
                yield GENERAL_DISCOUNT, \
                    line.price_unit * line.qty * line.discount / 100.0

    def _get_old_partner_ids(self, partners):
        """العملاء القدامى = من لديهم فواتير مبيعات مرحّلة بتاريخ سابق لبداية الفترة.

        نفس منطق حقل الاستوديو x_studio_selection_field_57p_1j3eak00d
        (New Customer ?) ولكن على مستوى فترة التقرير (للقسمين 1 و 5).
        """
        if not partners:
            return set()
        tz_date_from = fields.Datetime.context_timestamp(
            self, self.date_from).date()
        # sudo() ضيق النطاق: عملية تجميع (عدّ) فقط على فواتير العملاء لتحديد
        # جديد/قديم، حتى لا يفشل التقرير لمستخدم نقاط بيع بدون صلاحيات محاسبة.
        groups = self.env['account.move'].sudo().read_group(
            [
                ('partner_id', 'in', partners.ids),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '<', tz_date_from),
            ],
            ['partner_id'], ['partner_id'],
        )
        return {g['partner_id'][0] for g in groups if g.get('partner_id')}

    def _get_partner_invoice_history(self, partners):
        """تاريخ فواتير كل عميل (استعلام واحد) لمحاكاة حقول الاستوديو الثلاثة
        على مستوى كل فاتورة دون استعلامات متكررة لكل صف (تجنب N+1).

        يعيد: {partner_id: [(invoice_date, move_id), ...] مرتبة تصاعدياً}
        sudo() ضيق النطاق: يُقرأ التاريخ والمعرف فقط.
        """
        if not partners:
            return {}
        moves = self.env['account.move'].sudo().search_read(
            [
                ('partner_id', 'in', partners.ids),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '!=', False),
            ],
            ['partner_id', 'invoice_date', 'id'],
            order='invoice_date asc, id asc',
        )
        history = {}
        for m in moves:
            history.setdefault(m['partner_id'][0], []).append(
                (m['invoice_date'], m['id']))
        return history

    def _partner_invoice_stats(self, history, order):
        """محاكاة حقول الاستوديو الثلاثة على مستوى الطلب/الفاتورة:

        - آخر فاتورة  = آخر فاتورة مرحّلة بتاريخ <= تاريخ الطلب
          (نفس x_last_invoice_date)
        - الأيام منذ آخر فاتورة = الفرق عن آخر فاتورة بتاريخ < تاريخ الطلب
          (نفس x_days_since_last_invoice)
        - عميل جديد؟ = لا توجد فواتير سابقة بتاريخ < تاريخ الطلب
          (نفس x_studio_selection_field_57p_1j3eak00d)
        مع استبعاد فاتورة الطلب نفسها (id != record.id) في كل الحالات.
        """
        if not order.partner_id:
            return None, None, None
        odate = fields.Datetime.context_timestamp(
            self, order.date_order).date()
        own_move_id = order.account_move.id if order.account_move else None
        last = prev_strict = None
        for inv_date, move_id in history.get(order.partner_id.id, ()):
            if move_id == own_move_id:
                continue
            if inv_date > odate:
                break
            last = inv_date
            if inv_date < odate:
                prev_strict = inv_date
        days = (odate - prev_strict).days if prev_strict else None
        return last, days, prev_strict is None

    @staticmethod
    def _order_number(order):
        """رقم الفاتورة إن وُجدت، وإلا مرجع طلب نقطة البيع.

        قراءة اسم الفاتورة بـ sudo ضيق النطاق حتى لا يفشل التقرير
        لمستخدم نقاط بيع بدون صلاحيات محاسبة (يُقرأ رقم الفاتورة فقط).
        """
        if order.account_move:
            return order.account_move.sudo().name
        return order.name or order.pos_reference or '-'

    @staticmethod
    def _order_employee_name(order):
        """اسم الكاشير: الموظف إن كانت وحدة pos_hr مفعّلة، وإلا المستخدم."""
        if 'employee_id' in order._fields and order.employee_id:
            return order.employee_id.name
        return order.user_id.name or '-'

    def _split_customers(self, partner_ids, old_partner_ids):
        new = len([p for p in partner_ids if p not in old_partner_ids])
        return new, len(partner_ids) - new

    # ------------------------------------------------------------------
    # بيانات التقرير
    # ------------------------------------------------------------------
    def prepare_report_data(self):
        self.ensure_one()
        orders = self._get_orders()
        sales_orders = orders.filtered(lambda o: o.amount_total >= 0)
        refund_orders = orders - sales_orders

        all_partners = orders.mapped('partner_id')
        old_partner_ids = self._get_old_partner_ids(all_partners)
        discount_product_ids = self._get_global_discount_product_ids()
        invoice_history = self._get_partner_invoice_history(all_partners)

        # إجمالي الخصم لكل طلب (يُستخدم في القسمين 1 و 5)
        order_discounts = {}
        for order in sales_orders:
            total = sum(amount for _name, amount in
                        self._iter_order_discounts(
                            order, discount_product_ids))
            if total:
                order_discounts[order.id] = total

        data = {
            'company_name': self.env.company.name,
            'currency': 'ر.س',
            'date_from': self._fmt_dt(self.date_from),
            'date_to': self._fmt_dt(self.date_to),
            'printed_on': self._fmt_dt(fields.Datetime.now()),
            'config_names': '، '.join(self.config_ids.mapped('name')),
            'has_data': bool(orders),
        }
        # خانة اليوم: تظهر فقط للفترات الأقل من 48 ساعة (التقرير اليومي)
        data['show_day'] = self._is_short_period()
        if data['show_day']:
            data['day_name'], data['day_date'] = self._get_day_parts()

        data['section1'] = self._prepare_section_totals(
            sales_orders, refund_orders, old_partner_ids, order_discounts)
        data['section2'] = self._prepare_section_invoices(
            sales_orders, invoice_history)
        data['section3'] = self._prepare_section_invoices(
            refund_orders, invoice_history, refunds=True)
        data['section4'] = self._prepare_section_products(
            orders, discount_product_ids)
        data['section5'] = self._prepare_section_employees(
            sales_orders, refund_orders, old_partner_ids, order_discounts)
        data['section6'] = self._prepare_section_discounts(
            sales_orders, discount_product_ids)

        # ---------- مؤشرات الأداء التنفيذية ----------
        # grand_total في القسم الأول أصبح صافياً (بعد خصم المرتجعات)
        net = data['section1']['grand_total']
        refunds = abs(data['section3']['total'])
        gross = net + refunds
        n_customers = data['section1']['total']['customers']
        n_new = data['section1']['total']['new']
        if n_new == 1:
            customers_display = '%s (1 جديد)' % n_customers
        elif n_new > 1:
            customers_display = '%s (%s جدد)' % (n_customers, n_new)
        else:
            customers_display = str(n_customers)
        data['kpis'] = {
            'gross_fmt': self._fmt_amount(gross),
            'refunds_fmt': self._fmt_amount(refunds),
            'net_fmt': self._fmt_amount(net),
            'invoices': data['section1']['total']['count'],
            'avg_fmt': self._fmt_amount(
                net / data['section1']['total']['count']
                if data['section1']['total']['count'] else 0.0),
            'customers_display': customers_display,
            'discounts_fmt': self._fmt_amount(
                data['section6']['grand_total']),
        }
        return data

    # --- القسم الأول: إجمالي المبيعات لكل فرع ---------------------------
    def _prepare_section_totals(self, sales_orders, refund_orders,
                                old_partner_ids, order_discounts):
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            vals['total'] += order.amount_total
            vals['count'] += 1
            vals['discounts'] += order_discounts.get(order.id, 0.0)
            if order.partner_id:
                vals['partners'].add(order.partner_id.id)
        # خصم المرتجعات من فرعها: الإجمالي المعروض = صافي المبيعات
        for order in refund_orders:
            cfg = order.session_id.config_id
            vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            vals['total'] -= abs(order.amount_total)

        grand_total = sum(v['total'] for v in per_config.values())
        grand_discounts = sum(v['discounts'] for v in per_config.values())
        rows = []
        for vals in per_config.values():
            new, old = self._split_customers(vals['partners'], old_partner_ids)
            share = (vals['total'] / grand_total * 100.0) if grand_total else 0.0
            avg = (vals['total'] / vals['count']) if vals['count'] else 0.0
            rows.append({
                'name': vals['name'],
                'total': vals['total'],
                'total_fmt': self._fmt_amount(vals['total']),
                'share_fmt': '%{:.1f}'.format(share),
                'avg_fmt': self._fmt_amount(avg),
                'discounts_fmt': self._fmt_amount(vals['discounts']),
                'count': vals['count'],
                'customers': len(vals['partners']),
                'new': new,
                'old': old,
            })
        rows.sort(key=lambda r: r['total'], reverse=True)

        all_partner_ids = set()
        for vals in per_config.values():
            all_partner_ids |= vals['partners']
        t_new, t_old = self._split_customers(all_partner_ids, old_partner_ids)
        t_count = sum(r['count'] for r in rows)
        total_row = {
            'total_fmt': self._fmt_amount(grand_total),
            'share_fmt': '%100.0' if grand_total else '%0.0',
            'avg_fmt': self._fmt_amount(
                grand_total / t_count if t_count else 0.0),
            'discounts_fmt': self._fmt_amount(grand_discounts),
            'count': t_count,
            'customers': len(all_partner_ids),
            'new': t_new,
            'old': t_old,
        }
        return {'rows': rows, 'total': total_row, 'grand_total': grand_total}

    # --- القسمان الثاني والثالث: فواتير المبيعات / المرتجعات -----------
    def _prepare_section_invoices(self, orders, invoice_history,
                                  refunds=False):
        rows = []
        for order in orders:
            last_inv, days, is_new = self._partner_invoice_stats(
                invoice_history, order)
            rows.append({
                'date': self._fmt_dt(order.date_order),
                'number': self._order_number(order),
                'pos': order.session_id.config_id.name,
                'customer': order.partner_id.name or 'عميل نقدي',
                'phone': order.partner_id.mobile or order.partner_id.phone or '-',
                'is_new': ('نعم' if is_new else 'لا')
                          if order.partner_id else '-',
                'last_inv': last_inv.strftime('%Y-%m-%d')
                            if last_inv else '-',
                'days': days if days is not None else '-',
                'total': order.amount_total,
                'total_fmt': self._fmt_amount(abs(order.amount_total)),
            })
        # الترتيب تنازلياً حسب القيمة (للمرتجعات: الأكبر قيمةً مطلقة أولاً)
        rows.sort(key=lambda r: abs(r['total']), reverse=True)
        total = sum(r['total'] for r in rows)
        return {
            'rows': rows,
            'count': len(rows),
            'total': total,
            'total_fmt': self._fmt_amount(abs(total)),
        }

    # --- القسم الرابع: مبيعات المنتجات حسب الفئة ------------------------
    def _prepare_section_products(self, orders, discount_product_ids):
        categories = {}
        for line in orders.mapped('lines'):
            # استبعاد بنود مكافآت الخصم (قيم سالبة من برامج الولاء/العروض)
            if 'reward_id' in line._fields and line.reward_id \
                    and line.price_subtotal_incl <= 0:
                continue
            # استبعاد بنود الخصم العام (Global Discount) - تُعرض في قسم الخصومات
            if line.product_id.id in discount_product_ids:
                continue
            # بنود مكونات الكومبو (أودو 18): السعر موزع على المكونات بينما
            # سطر منتج الكومبو الأب صفري - نعيد نسب قيمة المكون وخصمه إلى
            # منتج الكومبو الأب وفئته، دون عد كميته (الكمية = كمية الكومبو
            # نفسها من سطر الأب، فيصبح متوسط سعر الوحدة = سعر الكومبو الكامل)
            combo_parent = line.combo_parent_id \
                if 'combo_parent_id' in line._fields else False
            is_component = bool(combo_parent)
            product = combo_parent.product_id if is_component \
                else line.product_id
            categ = product.categ_id
            cat_vals = categories.setdefault(categ.id, {
                'name': categ.display_name or 'غير مصنّف',
                'qty': 0.0, 'total': 0.0, 'discount': 0.0, 'products': {},
            })
            prod_vals = cat_vals['products'].setdefault(product.id, {
                'name': product.name,
                'qty': 0.0, 'total': 0.0, 'discount': 0.0,
            })
            # خصم البند اليدوي (النسبة) هو الخصم الوحيد المنسوب لمنتج محدد
            line_discount = (line.price_unit * line.qty * line.discount
                             / 100.0) if line.discount else 0.0
            line_qty = 0.0 if is_component else line.qty
            cat_vals['qty'] += line_qty
            cat_vals['total'] += line.price_subtotal_incl
            cat_vals['discount'] += line_discount
            prod_vals['qty'] += line_qty
            prod_vals['total'] += line.price_subtotal_incl
            prod_vals['discount'] += line_discount

        cat_rows = []
        for cat in categories.values():
            products = sorted(
                cat['products'].values(),
                key=lambda p: p['qty'], reverse=True)
            for p in products:
                p['qty_fmt'] = self._fmt_qty(p['qty'])
                p['total_fmt'] = self._fmt_amount(p['total'])
                p['discount_fmt'] = self._fmt_amount(p['discount'])
                p['avg_fmt'] = self._fmt_amount(
                    p['total'] / p['qty'] if p['qty'] else 0.0)
            cat_rows.append({
                'name': cat['name'],
                'product_count': len(products),
                'qty': cat['qty'],
                'qty_fmt': self._fmt_qty(cat['qty']),
                'total': cat['total'],
                'total_fmt': self._fmt_amount(cat['total']),
                'discount_fmt': self._fmt_amount(cat['discount']),
                'avg_fmt': self._fmt_amount(
                    cat['total'] / cat['qty'] if cat['qty'] else 0.0),
                'products': products,
            })
        cat_rows.sort(key=lambda c: c['qty'], reverse=True)
        total_qty = sum(c['qty'] for c in cat_rows)
        total_amount = sum(c['total'] for c in cat_rows)
        total_discount = sum(
            cat['discount'] for cat in categories.values())
        return {
            'categories': cat_rows,
            'total_qty_fmt': self._fmt_qty(total_qty),
            'total_fmt': self._fmt_amount(total_amount),
            'total_discount_fmt': self._fmt_amount(total_discount),
            'total_avg_fmt': self._fmt_amount(
                total_amount / total_qty if total_qty else 0.0),
        }

    # --- القسم الخامس: مبيعات الموظفين لكل فرع ---------------------------
    def _prepare_section_employees(self, sales_orders, refund_orders,
                                   old_partner_ids, order_discounts):
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            cfg_vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'employees': {},
            })
            emp_name = self._order_employee_name(order)
            emp_vals = cfg_vals['employees'].setdefault(emp_name, {
                'name': emp_name, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            emp_vals['total'] += order.amount_total
            emp_vals['count'] += 1
            emp_vals['discounts'] += order_discounts.get(order.id, 0.0)
            if order.partner_id:
                emp_vals['partners'].add(order.partner_id.id)
        # خصم المرتجعات من موظفها وفرعها: المعروض = صافي مبيعات الموظف
        for order in refund_orders:
            cfg = order.session_id.config_id
            cfg_vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'employees': {},
            })
            emp_name = self._order_employee_name(order)
            emp_vals = cfg_vals['employees'].setdefault(emp_name, {
                'name': emp_name, 'total': 0.0, 'count': 0,
                'partners': set(), 'discounts': 0.0,
            })
            emp_vals['total'] -= abs(order.amount_total)

        configs = []
        for cfg_vals in per_config.values():
            emp_rows = []
            cfg_partners = set()
            for emp in cfg_vals['employees'].values():
                new, old = self._split_customers(
                    emp['partners'], old_partner_ids)
                cfg_partners |= emp['partners']
                emp_rows.append({
                    'name': emp['name'],
                    'total': emp['total'],
                    'total_fmt': self._fmt_amount(emp['total']),
                    'count': emp['count'],
                    'avg_fmt': self._fmt_amount(
                        emp['total'] / emp['count'] if emp['count'] else 0.0),
                    'discounts_fmt': self._fmt_amount(emp['discounts']),
                    'customers': len(emp['partners']),
                    'new': new,
                    'old': old,
                })
            emp_rows.sort(key=lambda r: r['total'], reverse=True)
            c_new, c_old = self._split_customers(
                cfg_partners, old_partner_ids)
            cfg_total = sum(r['total'] for r in emp_rows)
            cfg_count = sum(r['count'] for r in emp_rows)
            cfg_discounts = sum(
                emp['discounts'] for emp in cfg_vals['employees'].values())
            configs.append({
                'name': cfg_vals['name'],
                'rows': emp_rows,
                'total': cfg_total,
                'subtotal': {
                    'total_fmt': self._fmt_amount(cfg_total),
                    'count': cfg_count,
                    'avg_fmt': self._fmt_amount(
                        cfg_total / cfg_count if cfg_count else 0.0),
                    'discounts_fmt': self._fmt_amount(cfg_discounts),
                    'customers': len(cfg_partners),
                    'new': c_new,
                    'old': c_old,
                },
            })
        configs.sort(key=lambda c: c['total'], reverse=True)
        return {'configs': configs}

    # --- القسم السادس: تحليل الخصومات -----------------------------------
    def _prepare_section_discounts(self, sales_orders, discount_product_ids):
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            cfg_vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'discounts': {},
            })
            for name, amount in self._iter_order_discounts(
                    order, discount_product_ids):
                entry = cfg_vals['discounts'].setdefault(
                    name, {'total': 0.0, 'orders': set()})
                entry['total'] += amount
                entry['orders'].add(order.id)

        configs = []
        grand_total = 0.0
        grand_orders = set()
        for cfg_vals in per_config.values():
            rows = []
            for name, entry in cfg_vals['discounts'].items():
                count = len(entry['orders'])
                rows.append({
                    'name': name,
                    'total': entry['total'],
                    'total_fmt': self._fmt_amount(entry['total']),
                    'count': count,
                    'avg_fmt': self._fmt_amount(
                        entry['total'] / count if count else 0.0),
                })
            if not rows:
                continue
            rows.sort(key=lambda r: r['total'], reverse=True)
            subtotal = sum(r['total'] for r in rows)
            cfg_orders = set()
            for entry in cfg_vals['discounts'].values():
                cfg_orders |= entry['orders']
            grand_total += subtotal
            grand_orders |= cfg_orders
            configs.append({
                'name': cfg_vals['name'],
                'rows': rows,
                'total': subtotal,
                'subtotal_fmt': self._fmt_amount(subtotal),
                'subtotal_count': len(cfg_orders),
                'subtotal_avg_fmt': self._fmt_amount(
                    subtotal / len(cfg_orders) if cfg_orders else 0.0),
            })
        configs.sort(key=lambda c: c['total'], reverse=True)
        return {
            'configs': configs,
            'grand_total': grand_total,
            'total_fmt': self._fmt_amount(grand_total),
            'total_count': len(grand_orders),
            'total_avg_fmt': self._fmt_amount(
                grand_total / len(grand_orders) if grand_orders else 0.0),
        }
