from odoo import models, fields, api
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # الحقل 1: قناة البيع - related شغال لأن move_id.x_studio_method_1 مش One2many
    x_channel = fields.Selection(
        related='move_id.x_studio_method_1',
        string='Channel',
        readonly=True,
        store=False,
    )

    # الحقل 2: جلسة POS - field عادي لأن pos_order_ids هو One2many
    x_pos_session_id = fields.Many2one(
        comodel_name='pos.session',
        string='POS Session',
        readonly=True,
    )

    # الحقل 3: الموظف - field عادي لأن pos_order_ids هو One2many
    x_pos_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='POS Employee',
        readonly=True,
    )

    @api.model
    def _select(self) -> SQL:
        original = super()._select()
        return SQL(
            '''%s
            , move.x_studio_method_1   AS x_channel
            , pos_order.session_id     AS x_pos_session_id
            , pos_order.employee_id    AS x_pos_employee_id
            ''',
            original,
        )

    @api.model
    def _from(self) -> SQL:
        original = super()._from()
        return SQL(
            '''%s
            LEFT JOIN pos_order ON pos_order.account_move = move.id
            ''',
            original,
        )
