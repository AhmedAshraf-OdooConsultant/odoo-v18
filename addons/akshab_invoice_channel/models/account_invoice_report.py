from odoo import models, fields, tools
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    # -----------------------------------------------------------------------
    # عدّل قيم الـ selection دي تتطابق مع x_studio_method_1 على account.move
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

    def init(self):
        """
        نعيد بناء الـ View بالكامل مع إضافة عمود x_channel.
        الاستراتيجية: نشيل الـ View الموجود لو كان موجود، وننشئه من الصفر
        بنفس الـ SQL الأصلية + عمود x_channel من account_move.
        """
        # نجيب جدول العملات
        currency_table = self.env['res.currency']._get_simple_currency_table(
            self.env.companies
        )

        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    line.id                                                     AS id,
                    move.id                                                     AS move_id,
                    move.name                                                   AS move_name,
                    move.journal_id                                             AS journal_id,
                    move.company_id                                             AS company_id,
                    move.company_currency_id                                    AS company_currency_id,
                    move.partner_id                                             AS partner_id,
                    move.commercial_partner_id                                  AS commercial_partner_id,
                    move.fiscal_position_id                                     AS fiscal_position_id,
                    move.invoice_user_id                                        AS invoice_user_id,
                    move.invoice_date                                           AS invoice_date,
                    move.invoice_date_due                                       AS invoice_date_due,
                    move.invoice_payment_term_id                                AS invoice_payment_term_id,
                    move.partner_bank_id                                        AS partner_bank_id,
                    move.invoice_currency_rate                                  AS invoice_currency_rate,
                    move.move_type                                              AS move_type,
                    move.state                                                  AS state,
                    move.payment_state                                          AS payment_state,
                    line.account_id                                             AS account_id,
                    line.product_id                                             AS product_id,
                    line.product_uom_id                                         AS product_uom_id,
                    line.currency_id                                            AS currency_id,
                    COALESCE(partner.country_id, commercial_partner.country_id) AS country_id,
                    line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0)
                        * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                                AS quantity,
                    line.price_subtotal
                        * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                                AS price_subtotal_currency,
                    -line.balance * account_currency_table.rate                 AS price_subtotal,
                    line.price_total
                        * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                                AS price_total,
                    -line.balance * account_currency_table.rate
                        / NULLIF(
                            line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0),
                            0.0
                        )
                        * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                                AS price_average,
                    CASE
                        WHEN move.move_type NOT IN ('out_invoice', 'out_receipt', 'out_refund') THEN 0.0
                        WHEN move.move_type = 'out_refund' THEN
                            account_currency_table.rate * (
                                -line.balance
                                + (line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0))
                                * COALESCE(product.standard_price -> line.company_id::text, to_jsonb(0.0))::float
                            )
                        ELSE
                            account_currency_table.rate * (
                                -line.balance
                                - (line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0))
                                * COALESCE(product.standard_price -> line.company_id::text, to_jsonb(0.0))::float
                            )
                    END                                                         AS price_margin,
                    account_currency_table.rate
                        * line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0)
                        * (CASE WHEN move.move_type IN ('out_invoice','in_refund','out_receipt') THEN -1 ELSE 1 END)
                        * COALESCE(product.standard_price -> line.company_id::text, to_jsonb(0.0))::float
                                                                                AS inventory_value,
                    move.amount_residual
                        * (CASE WHEN move.move_type IN ('in_invoice','in_receipt') THEN 1 ELSE -1 END)
                                                                                AS amount_residual,
                    move.x_studio_method_1                                      AS x_channel
                FROM account_move_line line
                    JOIN account_move move ON move.id = line.move_id
                    LEFT JOIN res_partner partner ON partner.id = line.partner_id
                    LEFT JOIN res_partner commercial_partner ON commercial_partner.id = move.commercial_partner_id
                    LEFT JOIN product_product product ON product.id = line.product_id
                    LEFT JOIN product_template uom_template ON uom_template.id = product.product_tmpl_id
                    LEFT JOIN uom_uom uom_line ON uom_line.id = line.product_uom_id
                    JOIN {currency_table} ON account_currency_table.company_id = line.company_id
                WHERE move.move_type IN (
                    'out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt'
                )
                AND line.parent_state = 'posted'
                AND line.display_type = 'product'
                AND line.account_id IS NOT NULL
            )
        """)
