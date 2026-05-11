from odoo import models, fields, tools


class AccountInvoiceReport(models.Model):
    """
    Extends account.invoice.report (an SQL View / _auto=False model)
    to include x_channel field sourced from move.x_studio_method_1.

    Because this is an SQL View, we cannot use store=True on a related field.
    Instead we override _query() to inject the column directly into the SELECT,
    and declare the field normally so Odoo can use it in Group By / Filters.
    """
    _inherit = 'account.invoice.report'

    # -------------------------------------------------------------------------
    # Field declaration
    # Adjust the selection values below to match exactly what you have in
    # x_studio_method_1 on account.move (the keys, not the labels).
    # Example: [('pos', 'POS'), ('online', 'Online'), ('trade', 'Trade Show')]
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

    # -------------------------------------------------------------------------
    # Override _query to inject the column into the SQL View
    # -------------------------------------------------------------------------
    def _query(self):
        """
        Call the original _query() from account.invoice.report, then wrap it
        to add move.x_studio_method_1 AS x_channel to every SELECT row.

        Strategy:
          - The original query is a WITH ... SELECT ... FROM ...
          - We wrap the whole thing as a sub-query and add the extra column.
          - This avoids copy-pasting the entire original query and stays
            upgrade-safe: only the wrapper changes.
        """
        original_query = super()._query()

        # The original _query() returns an SQL object (odoo.tools.SQL) in Odoo 17+
        # or a plain string in older versions. We handle both.
        try:
            from odoo.tools import SQL  # noqa: F401
            # Odoo 17 / 18 style: SQL object — convert to string for wrapping
            original_sql = str(original_query)
            is_sql_obj = True
        except ImportError:
            original_sql = original_query
            is_sql_obj = False

        wrapped = f"""
            SELECT
                sub.*,
                move.x_studio_method_1 AS x_channel
            FROM (
                {original_sql}
            ) sub
            JOIN account_move move ON move.id = sub.move_id
        """

        if is_sql_obj:
            try:
                from odoo.tools import SQL
                return SQL(wrapped)
            except Exception:
                return wrapped
        return wrapped

    def init(self):
        """Re-create the SQL view with the extra column."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                {self._query()}
            )
        """)
