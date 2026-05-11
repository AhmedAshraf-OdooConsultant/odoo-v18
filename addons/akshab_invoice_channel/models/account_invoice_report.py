from odoo import models, fields, tools


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
        الاستراتيجية:
        1. نخلي Odoo يعمل الـ View الأصلي أولاً عبر super().init()
        2. لو الـ View اتعمل: نقرأه من DB ونضيف x_channel عليه
        3. لو super().init() مش بيعمل View (Enterprise): نقرأ الـ View
           الموجود أصلاً في DB ونعمل wrapper عليه
        """
        # ---- محاولة 1: تشغيل super ثم قراءة الـ View ----
        try:
            super().init()
        except Exception:
            pass

        # ---- تحقق هل الـ View موجود دلوقتي ----
        self.env.cr.execute("""
            SELECT COUNT(*)
            FROM information_schema.views
            WHERE table_name = %s
        """, [self._table])
        view_exists = self.env.cr.fetchone()[0] > 0

        if view_exists:
            # اقرأ الـ SQL الأصلية من قاعدة البيانات
            self.env.cr.execute(
                "SELECT pg_get_viewdef(%s::regclass, true)", [self._table]
            )
            original_sql = self.env.cr.fetchone()[0]

            # أعد بناء الـ View مع إضافة x_channel
            tools.drop_view_if_exists(self.env.cr, self._table)
            self.env.cr.execute(f"""
                CREATE OR REPLACE VIEW {self._table} AS (
                    SELECT
                        sub.*,
                        move.x_studio_method_1 AS x_channel
                    FROM (
                        {original_sql}
                    ) sub
                    LEFT JOIN account_move move ON move.id = sub.move_id
                )
            """)
        else:
            # الـ View مش موجود على الإطلاق — مشكلة في depends أو التسلسل
            # نترك الـ init بدون تغيير ونسجل تحذير
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "akshab_invoice_channel: View '%s' not found after super().init(). "
                "x_channel field will not be available. "
                "Make sure the 'account' module is fully installed first.",
                self._table
            )
