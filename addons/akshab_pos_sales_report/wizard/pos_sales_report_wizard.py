# -*- coding: utf-8 -*-
import pytz

from odoo import api, fields, models


class AkshabPosSalesReportWizard(models.TransientModel):
    _name = 'akshab.pos.sales.report.wizard'
    _description = 'معالج تقرير مبيعات نقاط البيع - أخشاب البخور'

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
        'pos.config', string='نقاط البيع', required=True,
        default=lambda self: self.env['pos.config'].search([]))

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref(
            'akshab_pos_sales_report.action_report_pos_sales'
        ).report_action(self)

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
        """جميع طلبات نقاط البيع ضمن الفترة ونقاط البيع المحددة."""
        return self.env['pos.order'].search([
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('session_id.config_id', 'in', self.config_ids.ids),
        ])

    def _get_old_partner_ids(self, partners):
        """العملاء القدامى = من لديهم فواتير مبيعات مرحّلة بتاريخ سابق لبداية الفترة.

        نفس منطق حقل الاستوديو x_studio_selection_field_57p_1j3eak00d
        (New Customer ?) المبني على account.move ولكن على مستوى فترة التقرير:
        العميل يُعتبر "جديداً" إذا لم توجد له أي فاتورة عميل مرحّلة قبل
        بداية الفترة المحددة في التقرير.
        """
        if not partners:
            return set()
        tz_date_from = fields.Datetime.context_timestamp(
            self, self.date_from).date()
        groups = self.env['account.move'].read_group(
            [
                ('partner_id', 'in', partners.ids),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '<', tz_date_from),
            ],
            ['partner_id'], ['partner_id'],
        )
        return {g['partner_id'][0] for g in groups if g.get('partner_id')}

    @staticmethod
    def _order_number(order):
        """رقم الفاتورة إن وُجدت، وإلا مرجع طلب نقطة البيع."""
        if order.account_move:
            return order.account_move.name
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

        data = {
            'company_name': self.env.company.name,
            'currency': 'ر.س',
            'date_from': self._fmt_dt(self.date_from),
            'date_to': self._fmt_dt(self.date_to),
            'printed_on': self._fmt_dt(fields.Datetime.now()),
            'config_names': '، '.join(self.config_ids.mapped('name')),
            'has_data': bool(orders),
        }
        data['section1'] = self._prepare_section_totals(
            sales_orders, old_partner_ids)
        data['section2'] = self._prepare_section_invoices(sales_orders)
        data['section3'] = self._prepare_section_invoices(
            refund_orders, refunds=True)
        data['section4'] = self._prepare_section_products(orders)
        data['section5'] = self._prepare_section_employees(
            sales_orders, old_partner_ids)
        data['section6'] = self._prepare_section_discounts(sales_orders)
        return data

    # --- القسم الأول: إجمالي المبيعات لكل نقطة بيع ---------------------
    def _prepare_section_totals(self, sales_orders, old_partner_ids):
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'total': 0.0, 'count': 0, 'partners': set(),
            })
            vals['total'] += order.amount_total
            vals['count'] += 1
            if order.partner_id:
                vals['partners'].add(order.partner_id.id)

        rows = []
        for vals in per_config.values():
            new, old = self._split_customers(vals['partners'], old_partner_ids)
            rows.append({
                'name': vals['name'],
                'total': vals['total'],
                'total_fmt': self._fmt_amount(vals['total']),
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
        total_row = {
            'total_fmt': self._fmt_amount(sum(r['total'] for r in rows)),
            'count': sum(r['count'] for r in rows),
            'customers': len(all_partner_ids),
            'new': t_new,
            'old': t_old,
        }
        return {'rows': rows, 'total': total_row}

    # --- القسمان الثاني والثالث: فواتير المبيعات / المرتجعات -----------
    def _prepare_section_invoices(self, orders, refunds=False):
        rows = []
        for order in orders:
            rows.append({
                'date': self._fmt_dt(order.date_order),
                'number': self._order_number(order),
                'pos': order.session_id.config_id.name,
                'customer': order.partner_id.name or 'عميل نقدي',
                'phone': order.partner_id.mobile or order.partner_id.phone or '-',
                'total': order.amount_total,
                'total_fmt': self._fmt_amount(abs(order.amount_total)),
            })
        # الترتيب تنازلياً حسب القيمة (للمرتجعات: الأكبر قيمةً مطلقة أولاً)
        rows.sort(key=lambda r: abs(r['total']), reverse=True)
        total = sum(r['total'] for r in rows)
        return {
            'rows': rows,
            'count': len(rows),
            'total_fmt': self._fmt_amount(abs(total)),
        }

    # --- القسم الرابع: مبيعات المنتجات حسب الفئة ------------------------
    def _prepare_section_products(self, orders):
        categories = {}
        for line in orders.mapped('lines'):
            # استبعاد بنود مكافآت الخصم (قيم سالبة من برامج الولاء/الخصومات)
            if 'reward_id' in line._fields and line.reward_id \
                    and line.price_subtotal_incl <= 0:
                continue
            product = line.product_id
            categ = product.categ_id
            cat_vals = categories.setdefault(categ.id, {
                'name': categ.display_name or 'غير مصنّف',
                'qty': 0.0, 'total': 0.0, 'products': {},
            })
            prod_vals = cat_vals['products'].setdefault(product.id, {
                'name': product.display_name, 'qty': 0.0, 'total': 0.0,
            })
            cat_vals['qty'] += line.qty
            cat_vals['total'] += line.price_subtotal_incl
            prod_vals['qty'] += line.qty
            prod_vals['total'] += line.price_subtotal_incl

        cat_rows = []
        for cat in categories.values():
            products = sorted(
                cat['products'].values(),
                key=lambda p: p['qty'], reverse=True)
            for p in products:
                p['qty_fmt'] = self._fmt_qty(p['qty'])
                p['total_fmt'] = self._fmt_amount(p['total'])
            cat_rows.append({
                'name': cat['name'],
                'qty': cat['qty'],
                'qty_fmt': self._fmt_qty(cat['qty']),
                'total': cat['total'],
                'total_fmt': self._fmt_amount(cat['total']),
                'products': products,
            })
        cat_rows.sort(key=lambda c: c['qty'], reverse=True)
        return {
            'categories': cat_rows,
            'total_qty_fmt': self._fmt_qty(
                sum(c['qty'] for c in cat_rows)),
            'total_fmt': self._fmt_amount(
                sum(c['total'] for c in cat_rows)),
        }

    # --- القسم الخامس: مبيعات الموظفين لكل نقطة بيع ---------------------
    def _prepare_section_employees(self, sales_orders, old_partner_ids):
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            cfg_vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'employees': {},
            })
            emp_name = self._order_employee_name(order)
            emp_vals = cfg_vals['employees'].setdefault(emp_name, {
                'name': emp_name, 'total': 0.0, 'count': 0, 'partners': set(),
            })
            emp_vals['total'] += order.amount_total
            emp_vals['count'] += 1
            if order.partner_id:
                emp_vals['partners'].add(order.partner_id.id)

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
                    'customers': len(emp['partners']),
                    'new': new,
                    'old': old,
                })
            emp_rows.sort(key=lambda r: r['total'], reverse=True)
            c_new, c_old = self._split_customers(
                cfg_partners, old_partner_ids)
            configs.append({
                'name': cfg_vals['name'],
                'rows': emp_rows,
                'total': sum(r['total'] for r in emp_rows),
                'subtotal': {
                    'total_fmt': self._fmt_amount(
                        sum(r['total'] for r in emp_rows)),
                    'count': sum(r['count'] for r in emp_rows),
                    'customers': len(cfg_partners),
                    'new': c_new,
                    'old': c_old,
                },
            })
        configs.sort(key=lambda c: c['total'], reverse=True)
        return {'configs': configs}

    # --- القسم السادس: تحليل الخصومات -----------------------------------
    def _prepare_section_discounts(self, sales_orders):
        GENERAL = 'خصومات عامة'
        per_config = {}
        for order in sales_orders:
            cfg = order.session_id.config_id
            cfg_vals = per_config.setdefault(cfg.id, {
                'name': cfg.name, 'discounts': {},
            })
            for line in order.lines:
                # 1) بنود مكافآت برامج الخصم (الولاء / العروض / أكواد الخصم)
                if 'reward_id' in line._fields and line.reward_id \
                        and line.price_subtotal_incl < 0:
                    program = line.reward_id.program_id
                    name = program.name or line.reward_id.description \
                        or 'برنامج خصم'
                    cfg_vals['discounts'][name] = \
                        cfg_vals['discounts'].get(name, 0.0) \
                        + abs(line.price_subtotal_incl)
                # 2) الخصم اليدوي (نسبة يضيفها الكاشير على البند)
                elif line.discount:
                    amount = line.price_unit * line.qty * line.discount / 100.0
                    cfg_vals['discounts'][GENERAL] = \
                        cfg_vals['discounts'].get(GENERAL, 0.0) + amount

        configs = []
        grand_total = 0.0
        for cfg_vals in per_config.values():
            rows = [
                {'name': name, 'total': total,
                 'total_fmt': self._fmt_amount(total)}
                for name, total in cfg_vals['discounts'].items()
            ]
            if not rows:
                continue
            rows.sort(key=lambda r: r['total'], reverse=True)
            subtotal = sum(r['total'] for r in rows)
            grand_total += subtotal
            configs.append({
                'name': cfg_vals['name'],
                'rows': rows,
                'total': subtotal,
                'subtotal_fmt': self._fmt_amount(subtotal),
            })
        configs.sort(key=lambda c: c['total'], reverse=True)
        return {
            'configs': configs,
            'total_fmt': self._fmt_amount(grand_total),
        }
