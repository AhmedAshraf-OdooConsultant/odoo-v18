# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..report.stock_status_xlsx import StockStatusXlsx


class AkshabStockStatusWizard(models.TransientModel):
    """Stagnant / slow-moving / active items report."""
    _name = 'akshab.stock.status.wizard'
    _inherit = 'akshab.stock.report.base'
    _description = 'Akshab Item Status Report Wizard'

    _report_xmlid = 'akshab_stock_report.action_report_akshab_stock_status_pdf'
    _report_basename = 'تقرير حالة الأصناف'

    date_from = fields.Datetime(
        string='فترة تحليل المبيعات من', required=True,
        default=lambda self: fields.Datetime.now() - timedelta(days=90),
        help='بداية الفترة التي يُحتسب عليها متوسط البيع اليومي وأيام التغطية (تنتهي بتاريخ المخزون).')
    stagnant_days = fields.Integer(
        string='راكد: لم يُبع خلال (يوم)', default=90, required=True,
        help='يُعد الصنف راكداً إذا لم يُسجل له أي بيع خلال هذا العدد من الأيام قبل تاريخ المخزون.')
    slow_cover_days = fields.Integer(
        string='بطيء الحركة: تغطية أكثر من (يوم)', default=180, required=True,
        help='الصنف الذي يُباع لكن كميته تكفي لأكثر من هذا العدد من الأيام يُصنف بطيء الحركة (فائض).')
    reorder_cover_days = fields.Integer(
        string='إعادة طلب: تغطية أقل من (يوم)', default=15, required=True)
    show_stagnant = fields.Boolean(string='الأصناف الراكدة', default=True)
    show_slow = fields.Boolean(string='الأصناف بطيئة الحركة', default=True)
    show_active = fields.Boolean(string='الأصناف النشطة', default=True)
    show_out_of_stock = fields.Boolean(string='الأصناف النافدة التي لها طلب', default=True)
    show_transfers = fields.Boolean(
        string='إعادة التوزيع بين المستودعات', default=True,
        help='اقتراحات نقل الأصناف الراكدة/البطيئة من مستودع لا تُباع فيه إلى مستودع تُباع فيه (يظهر عند وجود أكثر من مستودع).')
    max_lines = fields.Integer(
        string='الحد الأقصى لأسطر الأصناف لكل فئة في PDF', default=0, required=True,
        help='0 = عرض جميع الأصناف. ملف الإكسل يحتوي دائماً على جميع الأصناف.')

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_from >= wiz.date_to:
                raise UserError(_('بداية فترة التحليل يجب أن تسبق تاريخ المخزون.'))

    @api.constrains('stagnant_days', 'slow_cover_days', 'reorder_cover_days')
    def _check_params(self):
        for wiz in self:
            if wiz.stagnant_days <= 0 or wiz.slow_cover_days <= 0 or wiz.reorder_cover_days < 0:
                raise UserError(_('قيم الأيام يجب أن تكون أرقاماً موجبة.'))

    def _engine_options(self):
        o = super()._engine_options()
        o.date_from = self.date_from
        o.stagnant_days = self.stagnant_days
        o.slow_cover_days = self.slow_cover_days
        o.new_days = 0          # this report has no "new" status: an unsold item is stagnant
        o.reorder_cover_days = self.reorder_cover_days
        o.show_active = self.show_active
        o.show_out_of_stock = self.show_out_of_stock
        o.max_lines = self.max_lines
        return o

    def _xlsx_builder(self, data):
        return StockStatusXlsx(self, data)
