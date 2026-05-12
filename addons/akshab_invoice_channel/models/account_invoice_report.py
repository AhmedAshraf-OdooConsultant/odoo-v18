from odoo import models, fields, api
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # -----------------------------------------------------------------------
    # الحقل 1: قناة البيع - related من move_id.x_studio_method_1
    # -----------------------------------------------------------------------
    x_channel = fields.Selection(
        related='move_id.x_studio_method_1',
        string='Channel',
        readonly=True,
        store=False,
    )

    # -----------------------------------------------------------------------
    # الحقل 2: جلسة POS - related من move_id.pos_order_ids.session_id
    # -----------------------------------------------------------------------
    x_pos_session_id = fields.Many2one(
        comodel_name='pos.session',
        related='move_id.pos_order_ids.session_id',
        string='POS Session',
        readonly=True,
        store=False,
    )

    # -----------------------------------------------------------------------
    # الحقل 3: الموظف - related من move_id.pos_order_ids.employee_id
    # -----------------------------------------------------------------------
    x_pos_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        related='move_id.pos_order_ids.employee_id',
        string='POS Employee',
        readonly=True,
        store=False,
    )

    @api.model
    def _select(self) -> SQL:
        original = super()._select()
        return SQL(
            '''%s
            , move.x_studio_method_1                AS x_channel
            , pos_order.session_id                  AS x_pos_session_id
            , pos_order.employee_id                 AS x_pos_employee_id
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
