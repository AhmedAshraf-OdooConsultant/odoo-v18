from odoo import models, fields, api, osv


class AccountReport(models.Model):
    _inherit = 'account.report'

    filter_hide_unknown_partner_lines = fields.Selection(
        string="Hide Lines with Unknown partner",
        selection=[('by_default', "Enabled by Default"), ('optional', "Optional"), ('never', "Never")],
        compute=lambda x: x._compute_report_option_filter('filter_hide_unknown_partner_lines', 'optional'), readonly=False, store=True, depends=['root_report_id'],
    )

    def _init_options_hide_unknown_partner_lines(self, options, previous_options):
        if self.filter_hide_unknown_partner_lines != 'never':
            previous_val = previous_options.get('hide_unknown_partner_lines')
            if previous_val is not None:
                options['hide_unknown_partner_lines'] = previous_val
            else:
                options['hide_unknown_partner_lines'] = self.filter_hide_unknown_partner_lines == 'by_default'
        else:
            options['hide_unknown_partner_lines'] = False


    def get_report_information(self, options):
        result = super().get_report_information(options)
        result['filters']['show_hide_unknown_partner_lines'] = self.filter_hide_unknown_partner_lines
        return result
