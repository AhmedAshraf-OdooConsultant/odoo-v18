from odoo import models, fields, api
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # -----------------------------------------------------------------------
    # الفيلد ذي صلة: يقرأ من move_id.x_studio_method_1 مباشرةً
    # لو غيّرت أو أضفت قيم في x_studio_method_1 على الفاتورة
    # هتظهر هنا أوتوماتيك بدون أي تعديل في الكود
    # -----------------------------------------------------------------------
    x_channel = fields.Selection(
        related='move_id.x_studio_method_1',
        string='Channel',
        readonly=True,
        store=False,
    )

    @api.model
    def _select(self) -> SQL:
        # نضيف x_channel للـ SQL View عشان يشتغل Group By عليه
        original = super()._select()
        return SQL(
            '%s , move.x_studio_method_1 AS x_channel',
            original,
        )
