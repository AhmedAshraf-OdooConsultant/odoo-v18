# -*- coding: utf-8 -*-

from . import models
from . import controllers
from . import common_lib
from . import wizard

from odoo.api import Environment, SUPERUSER_ID


def uninstall_hook(env):
    """
    Odoo 18: uninstall_hook receives env directly (not cr, registry).
    Clean up client actions and menus created by this module.
    """
    for rec in env['ks_dashboard_ninja.board'].search([]):
        try:
            if rec.ks_dashboard_client_action_id:
                rec.ks_dashboard_client_action_id.sudo().unlink()
        except Exception:
            pass
        try:
            if rec.ks_dashboard_menu_id:
                rec.ks_dashboard_menu_id.sudo().unlink()
        except Exception:
            pass
