# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..report.stock_turnover_xlsx import StockTurnoverXlsx


class AkshabStockTurnoverWizard(models.TransientModel):
    """Inventory turnover report (by category, then by product)."""
    _name = 'akshab.stock.turnover.wizard'
    _inherit = 'akshab.stock.report.base'
    _description = 'Akshab Inventory Turnover Report Wizard'

    _report_xmlid = 'akshab_stock_report.action_report_akshab_stock_turnover_pdf'
    _report_basename = 'تقرير معدل دوران المخزون'

    date_from = fields.Datetime(
        string='الفترة من', required=True,
        default=lambda self: fields.Datetime.now() - timedelta(days=90),
        help='بداية فترة احتساب تكلفة البضاعة المباعة ومخزون البداية.')
    coverage_days = fields.Integer(
        string='فترة احتساب متوسط البيع اليومي للتغطية (يوم)', default=90, required=True,
        help='عدد الأيام السابقة لتاريخ التقرير التي يُحسب عليها متوسط البيع اليومي، وتُبنى عليها أيام التغطية (Stock Coverage).')
    cogs_basis = fields.Selection([
        ('svl', 'تكلفة البضاعة المباعة الفعلية من طبقات التقييم (الافتراضي)'),
        ('unit_cost', 'كمية المبيعات × متوسط التكلفة'),
    ], string='أساس تكلفة المبيعات (COGS)', default='svl', required=True)
    top_n = fields.Integer(
        string='عدد الأصناف في قوائم الأكثر / الأقل / بلا دوران', default=10, required=True,
        help='عدد الأصناف المعروضة في كل قائمة من: الأصناف الأكثر دوراناً، الأقل دوراناً، وبلا دوران (القائمة الكاملة في الإكسل).')
    max_lines = fields.Integer(
        string='الحد الأقصى لأسطر الأصناف لكل فئة في PDF', default=0, required=True,
        help='0 = عرض جميع الأصناف. ملف الإكسل يحتوي دائماً على جميع الأصناف.')

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_from >= wiz.date_to:
                raise UserError(_('بداية الفترة يجب أن تسبق تاريخ المخزون (نهاية الفترة).'))

    @api.constrains('coverage_days', 'top_n')
    def _check_params(self):
        for wiz in self:
            if wiz.coverage_days <= 0:
                raise UserError(_('فترة احتساب متوسط البيع اليومي يجب أن تكون موجبة.'))
            if wiz.top_n <= 0 or wiz.top_n > 200:
                raise UserError(_('عدد الأصناف في القوائم يجب أن يكون بين 1 و200.'))

    def _engine_options(self):
        o = super()._engine_options()
        o.date_from = self.date_from
        o.coverage_days = self.coverage_days
        o.cogs_basis = self.cogs_basis
        o.top_n = self.top_n
        o.max_lines = self.max_lines
        return o

    def _xlsx_builder(self, data):
        return StockTurnoverXlsx(self, data)
