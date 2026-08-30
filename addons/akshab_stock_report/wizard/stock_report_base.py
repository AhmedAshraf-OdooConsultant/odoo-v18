# -*- coding: utf-8 -*-
import base64
from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from ..report.stock_report_engine import ReportOptions, StockReportEngine


class AkshabStockReportBase(models.AbstractModel):
    """Options shared by all Akshab inventory report wizards (mixin)."""
    _name = 'akshab.stock.report.base'
    _description = 'Akshab inventory report – common options'

    company_id = fields.Many2one(
        'res.company', string='الشركة', required=True,
        default=lambda self: self.env.company)
    date_to = fields.Datetime(
        string='تاريخ المخزون (حتى)', required=True,
        default=fields.Datetime.now,
        help='يُحتسب المخزون والأعمار حتى هذا التاريخ. التاريخ الحالي يعتمد على الأرصدة الفعلية (stock.quant)، '
             'والتاريخ السابق يعاد بناؤه من حركات المخزون المنجزة.')
    warehouse_ids = fields.Many2many(
        'stock.warehouse', string='الفروع / المستودعات',
        domain="[('company_id', '=', company_id)]",
        help='اتركه فارغاً لتضمين جميع الفروع. يمكن اختيار أكثر من فرع.')
    location_ids = fields.Many2many(
        'stock.location', string='المواقع',
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
        help='اختياري: حصر التقرير في مواقع داخلية معينة (تشمل المواقع الفرعية). يمكن اختيار أكثر من موقع.')
    categ_ids = fields.Many2many(
        'product.category', string='فئات الأصناف',
        help='اتركه فارغاً لتضمين جميع الفئات (تشمل الفئات الفرعية). يمكن اختيار أكثر من فئة.')
    product_ids = fields.Many2many(
        'product.product', string='أصناف محددة',
        domain="[('is_storable', '=', True)]",
        help='اختياري: حصر التقرير في أصناف معينة. يمكن اختيار أكثر من صنف.')
    cost_basis = fields.Selection([
        ('svl', 'متوسط التكلفة من طبقات التقييم (الافتراضي)'),
        ('standard', 'التكلفة المسجلة على الصنف'),
    ], string='أساس تقييم المخزون', default='svl', required=True)

    # Excel download
    xlsx_file = fields.Binary(string='ملف الإكسل', readonly=True)
    xlsx_filename = fields.Char(string='اسم الملف', readonly=True)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        self.warehouse_ids = self.warehouse_ids.filtered(lambda w: w.company_id == self.company_id)
        self.location_ids = self.location_ids.filtered(lambda loc: loc.company_id == self.company_id)

    # ------------------------------------------------------------------
    # To be defined by each report wizard
    # ------------------------------------------------------------------
    _report_xmlid = None          # ir.actions.report xml id
    _report_basename = 'تقرير المخزون'

    def _xlsx_builder(self, data):
        raise NotImplementedError()

    def _engine_options(self):
        """Common options; report wizards extend the returned ReportOptions."""
        self.ensure_one()
        return ReportOptions(
            company=self.company_id,
            date_to=self.date_to,
            warehouse_ids=self.warehouse_ids,
            location_ids=self.location_ids,
            categ_ids=self.categ_ids,
            product_ids=self.product_ids,
            cost_basis=self.cost_basis,
        )

    def _check_company_access(self):
        """The engine reads stock data with SQL (no record rules): only allow companies the
        user belongs to."""
        self.ensure_one()
        if self.company_id not in self.env.user.company_ids and not self.env.su:
            raise AccessError(_('لا تملك صلاحية عرض بيانات الشركة %s.') % self.company_id.sudo().display_name)

    def _build_report_data(self):
        """Compute the full report data structure (used by both PDF and XLSX)."""
        self.ensure_one()
        self._check_company_access()
        return StockReportEngine(self, self._engine_options()).build()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_print_pdf(self):
        self.ensure_one()
        if not self._report_xmlid:
            raise UserError(_('لم يتم ضبط تقرير PDF لهذه النافذة.'))
        return self.env.ref(self._report_xmlid).report_action(self, config=False)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._build_report_data()
        content = self._xlsx_builder(data).build()
        filename = '%s %s.xlsx' % (self._report_basename, data['meta']['date_to_display'][:10])
        self.write({
            'xlsx_file': base64.b64encode(content),
            'xlsx_filename': filename,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/xlsx_file/%s?download=true' % (self._name, self.id, quote(filename)),
            'target': 'self',
        }
