# -*- coding: utf-8 -*-
from odoo import api, models


class ReportAkshabPosWeekly(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_weekly_doc'
    _description = 'تقرير المبيعات الأسبوعي - أخشاب البخور'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.weekly.report.wizard'].browse(docids)
        wizard = wizards[:1]
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.weekly.report.wizard',
            'docs': wizards,
            'company': self.env.company,
            'data': wizard.prepare_weekly_report_data() if wizard else {},
        }
