# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..report.stock_report_xlsx import StockReportXlsx


class AkshabStockReportWizard(models.TransientModel):
    """Comprehensive inventory status report (aging + status + recommendations)."""
    _name = 'akshab.stock.report.wizard'
    _inherit = 'akshab.stock.report.base'
    _description = 'Akshab Inventory Status Report Wizard'

    _report_xmlid = 'akshab_stock_report.action_report_akshab_stock_pdf'
    _report_basename = 'تقرير المخزون'

    # ------------------------------------------------------------------
    # Analysis parameters
    # ------------------------------------------------------------------
    sales_days = fields.Integer(
        string='فترة تحليل المبيعات (يوم)', default=90, required=True,
        help='عدد الأيام السابقة لتاريخ التقرير التي يُحتسب عليها متوسط البيع اليومي وأيام التغطية.')
    stagnant_days = fields.Integer(
        string='معيار الركود: لم يُبع خلال (يوم)', default=90, required=True,
        help='يُعد الصنف راكداً إذا لم يُسجل له أي بيع خلال هذا العدد من الأيام.')
    new_days = fields.Integer(
        string='الصنف جديد إذا استُلم خلال (يوم)', default=30, required=True,
        help='الأصناف التي استُلمت لأول مرة خلال هذه المدة ولم تُبع بعد تُصنف "جديدة" ولا تُعد راكدة.')
    slow_cover_days = fields.Integer(
        string='حد بطء الحركة: تغطية أكثر من (يوم)', default=180, required=True,
        help='الصنف الذي يُباع لكن كميته تكفي لأكثر من هذا العدد من الأيام يُصنف "بطيء الحركة / فائض".')
    reorder_cover_days = fields.Integer(
        string='حد إعادة الطلب: تغطية أقل من (يوم)', default=15, required=True,
        help='الصنف النشط الذي تقل تغطيته عن هذا العدد من الأيام يُقترح إعادة طلبه.')
    liquidation_discount = fields.Float(
        string='خصم التصفية المقترح (%)', default=30.0, required=True,
        help='نسبة الخصم المستخدمة لتقدير السيولة المتوقعة من بيع الأصناف الراكدة. '
             'يُخفض تلقائياً لكل صنف بحيث لا يقل سعر البيع عن التكلفة.')

    # Aging buckets (upper bound of each bucket in days)
    bucket_1 = fields.Integer(string='الفئة العمرية ١ حتى (يوم)', default=30, required=True)
    bucket_2 = fields.Integer(string='الفئة العمرية ٢ حتى (يوم)', default=60, required=True)
    bucket_3 = fields.Integer(string='الفئة العمرية ٣ حتى (يوم)', default=90, required=True)
    bucket_4 = fields.Integer(string='الفئة العمرية ٤ حتى (يوم)', default=180, required=True)
    bucket_5 = fields.Integer(string='الفئة العمرية ٥ حتى (يوم)', default=365, required=True)

    # Output options
    max_lines = fields.Integer(
        string='الحد الأقصى لأسطر الجداول التفصيلية في PDF', default=50, required=True,
        help='0 = عرض جميع الأصناف. ملف الإكسل يحتوي دائماً على جميع الأصناف.')
    show_active = fields.Boolean(string='إظهار الأصناف النشطة (الأكثر حركة)', default=True)
    show_out_of_stock = fields.Boolean(string='إظهار الأصناف النافدة التي لها طلب', default=True)
    show_category_aging = fields.Boolean(string='إظهار مصفوفة الأعمار حسب الفئة', default=True)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @api.constrains('bucket_1', 'bucket_2', 'bucket_3', 'bucket_4', 'bucket_5')
    def _check_buckets(self):
        for wiz in self:
            b = [wiz.bucket_1, wiz.bucket_2, wiz.bucket_3, wiz.bucket_4, wiz.bucket_5]
            if any(x <= 0 for x in b) or any(b[i] >= b[i + 1] for i in range(4)):
                raise UserError(_('يجب أن تكون حدود الفئات العمرية أرقاماً موجبة ومتصاعدة (مثال: 30، 60، 90، 180، 365).'))

    @api.constrains('sales_days', 'stagnant_days', 'new_days', 'slow_cover_days', 'reorder_cover_days')
    def _check_days(self):
        for wiz in self:
            if wiz.sales_days <= 0 or wiz.stagnant_days <= 0 or wiz.new_days < 0 \
                    or wiz.slow_cover_days <= 0 or wiz.reorder_cover_days < 0:
                raise UserError(_('قيم الأيام يجب أن تكون أرقاماً موجبة.'))

    @api.constrains('liquidation_discount')
    def _check_discount(self):
        for wiz in self:
            if wiz.liquidation_discount < 0 or wiz.liquidation_discount >= 100:
                raise UserError(_('نسبة خصم التصفية يجب أن تكون بين 0 و 99.'))

    # ------------------------------------------------------------------
    def _engine_options(self):
        o = super()._engine_options()
        o.sales_days = self.sales_days
        o.stagnant_days = self.stagnant_days
        o.new_days = self.new_days
        o.slow_cover_days = self.slow_cover_days
        o.reorder_cover_days = self.reorder_cover_days
        o.liquidation_discount = self.liquidation_discount
        o.buckets = [self.bucket_1, self.bucket_2, self.bucket_3, self.bucket_4, self.bucket_5]
        o.old_days = self.bucket_4
        o.max_lines = self.max_lines
        o.show_active = self.show_active
        o.show_out_of_stock = self.show_out_of_stock
        o.show_category_aging = self.show_category_aging
        return o

    def _xlsx_builder(self, data):
        return StockReportXlsx(self, data)
