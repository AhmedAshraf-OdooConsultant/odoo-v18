from odoo import models, fields, tools


class AccountInvoiceReport(models.Model):
    """
    Extends account.invoice.report to add x_channel (Channel) field
    sourced from move.x_studio_method_1, with full Group By support.

    Strategy: override init() to rebuild the SQL View adding the extra column
    via a wrapper SELECT, without copy-pasting the entire original query.
    We read the original view definition from the DB after the parent init()
    runs, then replace the view with an augmented version.
    """
    _inherit = 'account.invoice.report'

    # -------------------------------------------------------------------------
    # Adjust the selection keys/labels to match x_studio_method_1 on account.move
    # -------------------------------------------------------------------------
    x_channel = fields.Selection(
        selection=[
            ('pos', 'POS'),
            ('online', 'Online'),
            ('trade_show', 'Trade Show'),
        ],
        string='Channel',
        readonly=True,
    )

    def init(self):
        # 1. Let the original module create the view normally
        super().init()

        # 2. Read the original view SQL from the DB
        self.env.cr.execute("""
            SELECT pg_get_viewdef(%s, true)
        """, [self._table])
        row = self.env.cr.fetchone()
        if not row:
            return
        original_view_sql = row[0]

        # 3. Drop and recreate the view with x_channel added
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    sub.*,
                    move.x_studio_method_1 AS x_channel
                FROM (
                    {original_view_sql}
                ) sub
                LEFT JOIN account_move move ON move.id = sub.move_id
            )
        """)
