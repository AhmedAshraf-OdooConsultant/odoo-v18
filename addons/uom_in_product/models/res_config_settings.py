# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettingsInherit(models.TransientModel):
    """ This model represents res.config.settings."""
    _inherit = 'res.config.settings'

    set_uom_to_reference = fields.Boolean(string="Set UoM to Reference",
                                          config_parameter='uom_in_product.set_uom_to_reference',
                                          default=False,
                                          help="Set UoM to Reference for all products")