# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..report.stock_aging_xlsx import StockAgingXlsx


class AkshabStockAgingWizard(models.TransientModel):
    """Inventory aging report (by category, then by product)."""
    _name = 'akshab.stock.aging.wizard'
    _inherit = 'akshab.stock.report.base'
    _description = 'Akshab Inventory Aging Report Wizard'

    _report_xmlid = 'akshab_stock_report.action_report_akshab_stock_aging_pdf'
    _report_basename = 'تقرير أعمار المخزون'

    bucket_mode = fields.Selection([
        ('step', 'فئات متساوية (كل N يوم)'),
        ('custom', 'حدود مخصصة'),
    ], string='طريقة تقسيم الأعمار', default='step', required=True)
    bucket_days = fields.Integer(
        string='طول الفئة العمرية (يوم)', default=30, required=True,
        help='مثال: 30 → 0–30، 31–60، 61–90 ... ثم "أكثر من" آخر حد.')
    bucket_count = fields.Integer(
        string='عدد الفئات', default=6, required=True,
        help='عدد الفئات المتساوية قبل فئة "أكثر من". مثال: 30 يوم × 6 فئات = حتى 180 يوم ثم أكثر من 180.')
    bucket_1 = fields.Integer(string='الفئة ١ حتى (يوم)', default=30)
    bucket_2 = fields.Integer(string='الفئة ٢ حتى (يوم)', default=60)
    bucket_3 = fields.Integer(string='الفئة ٣ حتى (يوم)', default=90)
    bucket_4 = fields.Integer(string='الفئة ٤ حتى (يوم)', default=180)
    bucket_5 = fields.Integer(string='الفئة ٥ حتى (يوم)', default=365)
    show_warehouse_split = fields.Boolean(string='إظهار توزيع الأعمار حسب الفرع', default=True)
    show_value = fields.Boolean(string='إظهار القيمة بجانب الكمية في جداول الأصناف', default=True)
    max_lines = fields.Integer(
        string='الحد الأقصى لأسطر الأصناف لكل فئة في PDF', default=0, required=True,
        help='0 = عرض جميع الأصناف. ملف الإكسل يحتوي دائماً على جميع الأصناف.')

    @api.constrains('bucket_mode', 'bucket_days', 'bucket_count', 'bucket_1', 'bucket_2', 'bucket_3', 'bucket_4', 'bucket_5')
    def _check_buckets(self):
        for wiz in self:
            if wiz.bucket_mode == 'step':
                if wiz.bucket_days <= 0 or wiz.bucket_count <= 0 or wiz.bucket_count > 24:
                    raise UserError(_('طول الفئة العمرية يجب أن يكون موجباً، وعدد الفئات بين 1 و24.'))
            else:
                b = [wiz.bucket_1, wiz.bucket_2, wiz.bucket_3, wiz.bucket_4, wiz.bucket_5]
                if any(x <= 0 for x in b) or any(b[i] >= b[i + 1] for i in range(4)):
                    raise UserError(_('يجب أن تكون حدود الفئات العمرية أرقاماً موجبة ومتصاعدة.'))

    def _buckets(self):
        if self.bucket_mode == 'step':
            return [self.bucket_days * i for i in range(1, self.bucket_count + 1)]
        return [self.bucket_1, self.bucket_2, self.bucket_3, self.bucket_4, self.bucket_5]

    def _engine_options(self):
        o = super()._engine_options()
        o.buckets = self._buckets()
        # the last bucket ("more than X days") is the only "old stock" figure of this report
        o.old_days = o.buckets[-1]
        o.max_lines = self.max_lines
        o.show_category_aging = self.show_warehouse_split
        return o

    def _xlsx_builder(self, data):
        return StockAgingXlsx(self, data)
