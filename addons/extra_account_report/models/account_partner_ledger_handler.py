from odoo import models
from collections import defaultdict

class PartnerLedgerHandler(models.AbstractModel):
    _inherit = 'account.partner.ledger.report.handler'

    def _get_custom_display_config(self):
        config = super()._get_custom_display_config()
        config['components']['AccountReportFilters'] = 'extra_account_report.HideUnknownPartnerLinesFilters'
        return config


    def _build_partner_lines(self, report, options, level_shift=0):
        lines = []

        totals_by_column_group = {
            column_group_key: {
                total: 0.0
                for total in ['debit', 'credit', 'amount', 'balance']
            }
            for column_group_key in options['column_groups']
        }

        partners_results = self._query_partners(report, options)

        # === Apply filters up front ===
        if options.get('hide_unknown_partner_lines'):
            partners_results = [
                (partner, results)
                for partner, results in partners_results
                if partner is not None
            ]

        if options.get('hide_0_lines'):
            filtered_partners = []
            for partner, results in partners_results:
                all_balances_zero = True
                for column_group_key in options['column_groups']:
                    balance = results.get(column_group_key, {}).get('balance', 0.0)
                    if not self.env.company.currency_id.is_zero(balance):
                        all_balances_zero = False
                        break
                if not all_balances_zero:
                    filtered_partners.append((partner, results))
            partners_results = filtered_partners

        # === Build lines ===
        search_filter = options.get('filter_search_bar', '')
        accept_unknown_in_filter = search_filter.lower() in self._get_no_partner_line_label().lower()

        for partner, results in partners_results:
            if (
                    options['export_mode'] == 'print'
                    and search_filter
                    and not partner
                    and not accept_unknown_in_filter
            ):
                continue

            partner_values = defaultdict(dict)

            for column_group_key in options['column_groups']:
                partner_sum = results.get(column_group_key, {})

                debit = partner_sum.get('debit', 0.0)
                credit = partner_sum.get('credit', 0.0)
                amount = partner_sum.get('amount', 0.0)
                balance = partner_sum.get('balance', 0.0)

                partner_values[column_group_key]['debit'] = debit
                partner_values[column_group_key]['credit'] = credit
                partner_values[column_group_key]['amount'] = amount
                partner_values[column_group_key]['balance'] = balance

                totals_by_column_group[column_group_key]['debit'] += debit
                totals_by_column_group[column_group_key]['credit'] += credit
                totals_by_column_group[column_group_key]['amount'] += amount
                totals_by_column_group[column_group_key]['balance'] += balance

            lines.append(
                self._get_report_line_partners(
                    options,
                    partner,
                    partner_values,
                    level_shift=level_shift
                )
            )

        return lines, totals_by_column_group
