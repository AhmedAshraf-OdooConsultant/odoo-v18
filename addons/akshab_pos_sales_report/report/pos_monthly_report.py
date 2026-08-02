# -*- coding: utf-8 -*-
"""نماذج التقرير الشهري + أدوات دمج الأجزاء وترقيم الصفحات.

التقرير المدمج يُبنى من أربعة أجزاء تُرندر مستقلة (المحتوى، الملخص،
وجزء لكل قناة) ثم تُدمج بـ pypdf ويُختم كل صفحة برقمها عبر reportlab -
وكلاهما ضمن تبعيات أودو القياسية."""
import io

from odoo import models


def pdf_page_count(pdf_bytes):
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def merge_and_stamp(part_bytes_list):
    """يدمج أجزاء PDF بالترتيب ويختم 'N / M' أسفل يسار كل صفحة."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    writer = PdfWriter()
    for part in part_bytes_list:
        reader = PdfReader(io.BytesIO(part))
        for page in reader.pages:
            writer.add_page(page)
    total = len(writer.pages)
    for i, page in enumerate(writer.pages, 1):
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFont('Helvetica', 7.5)
        c.setFillColorRGB(0.45, 0.42, 0.36)
        c.drawString(14, 8, '%d / %d' % (i, total))
        c.save()
        buf.seek(0)
        overlay = PdfReader(buf).pages[0]
        page.merge_page(overlay)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class PosMonthlyReport(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_monthly_doc'
    _description = 'تقرير المبيعات الشهري (الملخص) - أخشاب البخور'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.monthly.report.wizard'].browse(docids)
        report_data = (data or {}).get('monthly_data') \
            or wizards.prepare_monthly_report_data()
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.monthly.report.wizard',
            'docs': wizards,
            'data': report_data,
        }


class PosMonthlyChannelReport(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_monthly_channel_doc'
    _description = 'تقرير المبيعات الشهري (جزء قناة) - أخشاب البخور'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.monthly.report.wizard'].browse(docids)
        report_data = (data or {}).get('monthly_data') \
            or wizards.prepare_monthly_report_data()
        idx = (data or {}).get('channel_index', 0)
        channels = report_data.get('channels') or []
        channel = channels[idx] if idx < len(channels) else {}
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.monthly.report.wizard',
            'docs': wizards,
            'data': report_data,
            'channel': channel,
        }


class PosMonthlyTocReport(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_monthly_toc_doc'
    _description = 'تقرير المبيعات الشهري (صفحة المحتوى) - أخشاب البخور'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.monthly.report.wizard'].browse(docids)
        report_data = (data or {}).get('monthly_data') or {}
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.monthly.report.wizard',
            'docs': wizards,
            'data': report_data,
            'toc_entries': (data or {}).get('toc_entries') or [],
        }


class PosPeriodReport(models.AbstractModel):
    _name = 'report.akshab_pos_sales_report.report_pos_period_doc'
    _description = 'تقرير المبيعات للفترة - أخشاب البخور'

    def _get_report_values(self, docids, data=None):
        wizards = self.env['akshab.pos.period.report.wizard'].browse(docids)
        report_data = (data or {}).get('monthly_data') \
            or wizards.prepare_monthly_report_data()
        return {
            'doc_ids': docids,
            'doc_model': 'akshab.pos.period.report.wizard',
            'docs': wizards,
            'data': report_data,
        }
