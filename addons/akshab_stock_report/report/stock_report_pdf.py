# -*- coding: utf-8 -*-
from odoo import api, models

from .stock_report_engine import fmt_money, fmt_qty, fmt_pct, fmt_int, fmt_ratio, to_arabic_indic


class AkshabReportMixin:
    """Shared _get_report_values for the four report models."""
    _wizard_model = None

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env[self._wizard_model].browse(docids)
        reports = []
        for wizard in wizards:
            reports.append({'wizard': wizard, 'data': wizard._build_report_data()})
        return {
            'doc_ids': docids,
            'doc_model': self._wizard_model,
            'docs': wizards,
            'reports': reports,
            # formatting helpers exposed to QWeb
            'money': fmt_money,
            'qty': fmt_qty,
            'pct': fmt_pct,
            'num': fmt_int,
            'ratio': fmt_ratio,
            'ar': to_arabic_indic,
            'limit': self._limit,
        }

    @staticmethod
    def _limit(rows, max_lines):
        if not max_lines or max_lines <= 0:
            return rows
        return rows[:max_lines]


class AkshabStockReportPdf(AkshabReportMixin, models.AbstractModel):
    _name = 'report.akshab_stock_report.report_akshab_stock_document'
    _description = 'Akshab Inventory Status Report (PDF)'
    _wizard_model = 'akshab.stock.report.wizard'


class AkshabStockAgingPdf(AkshabReportMixin, models.AbstractModel):
    _name = 'report.akshab_stock_report.report_aging_doc'
    _description = 'Akshab Inventory Aging Report (PDF)'
    _wizard_model = 'akshab.stock.aging.wizard'


class AkshabStockTurnoverPdf(AkshabReportMixin, models.AbstractModel):
    _name = 'report.akshab_stock_report.report_turnover_doc'
    _description = 'Akshab Inventory Turnover Report (PDF)'
    _wizard_model = 'akshab.stock.turnover.wizard'


class AkshabStockStatusPdf(AkshabReportMixin, models.AbstractModel):
    _name = 'report.akshab_stock_report.report_status_doc'
    _description = 'Akshab Item Status Report (PDF)'
    _wizard_model = 'akshab.stock.status.wizard'
