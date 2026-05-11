from odoo import models, fields, api
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # -----------------------------------------------------------------------
    # عدّل قيم الـ selection دي تتطابق تماماً مع x_studio_method_1 على account.move
    # روح Settings > Technical > Fields > ابحث x_studio_method_1 في account.move
    # -----------------------------------------------------------------------
    x_channel = fields.Selection(
        selection=[
            ('pos', 'POS'),
            ('online', 'Online'),
            ('trade_show', 'Trade Show'),
        ],
        string='Channel',
        readonly=True,
    )

    @api.model
    def _select(self) -> SQL:
        # نجيب الـ SELECT الأصلية ونضيف عليها x_channel
        original = super()._select()
        return SQL(
            '%s , move.x_studio_method_1 AS x_channel',
            original,
        )
