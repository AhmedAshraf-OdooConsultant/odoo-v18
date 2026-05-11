import logging
from odoo.tools import drop_view_if_exists

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    يشتغل بعد ما الأدون يتثبت بالكامل.
    في اللحظة دي، الـ account_invoice_report View بيكون موجود بالتأكيد.
    نقرأه من DB ونضيف عليه عمود x_channel.
    """
    cr = env.cr
    table = 'account_invoice_report'

    # تحقق إن الـ View موجود
    cr.execute("""
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_name = %s
    """, [table])
    view_exists = cr.fetchone()[0] > 0

    if not view_exists:
        _logger.error(
            "post_init_hook: View '%s' not found! "
            "x_channel column will NOT be added.", table
        )
        return

    # اقرأ الـ SQL الأصلية من DB
    cr.execute("SELECT pg_get_viewdef(%s::regclass, true)", [table])
    original_sql = cr.fetchone()[0]

    _logger.info("post_init_hook: Rebuilding '%s' to add x_channel...", table)

    drop_view_if_exists(cr, table)
    cr.execute(f"""
        CREATE OR REPLACE VIEW {table} AS (
            SELECT
                sub.*,
                move.x_studio_method_1 AS x_channel
            FROM (
                {original_sql}
            ) sub
            LEFT JOIN account_move move ON move.id = sub.move_id
        )
    """)

    _logger.info("post_init_hook: View '%s' rebuilt successfully with x_channel.", table)
