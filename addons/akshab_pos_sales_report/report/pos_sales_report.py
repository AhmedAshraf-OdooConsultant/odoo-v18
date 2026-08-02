# -*- coding: utf-8 -*-
from odoo import api, models


class ReportAkshabPosSales(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_sales_doc'
    _description = 'تقرير مبيعات نقاط البيع - أخشاب البخور'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.sales.report.wizard'].browse(docids)
        wizard = wizards[:1]
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.sales.report.wizard',
            'docs': wizards,
            'company': self.env.company,
            'data': wizard.prepare_report_data() if wizard else {},
        }
