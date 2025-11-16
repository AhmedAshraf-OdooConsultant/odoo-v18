# custom_asset_report_dates/models/account_asset_report_handler.py

# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.tools import format_date, SQL, Query
from collections import defaultdict

MAX_NAME_LENGTH = 50


class AssetsReportCustomHandler(models.AbstractModel):
    _inherit = 'account.asset.report.handler'

    def _custom_options_initializer(self, report, options, previous_options):
        """
        This function is overridden to add new columns to the report layout.
        """
        super()._custom_options_initializer(report, options, previous_options)

        characteristics_group_key = None
        insertion_point = -1
        for i, col in enumerate(options['columns']):
            if col.get('expression_label') == 'method':
                characteristics_group_key = col.get('column_group_key')
                insertion_point = i + 1
                break

        if insertion_point != -1 and characteristics_group_key:
            new_columns = [
                {'name': _('Fixed Asset Account'), 'expression_label': 'fixed_asset_account', 'figure_type': 'text', 'column_group_key': characteristics_group_key},
                {'name': _('Depreciation Account'), 'expression_label': 'depreciation_account', 'figure_type': 'text', 'column_group_key': characteristics_group_key},
                {'name': _('Expense Account'), 'expression_label': 'expense_account', 'figure_type': 'text', 'column_group_key': characteristics_group_key},
            ]

            options['columns'][insertion_point:insertion_point] = new_columns

            for subheader in options.get('custom_columns_subheaders', []):
                if subheader['name'] == _("Characteristics"):
                    subheader['colspan'] = 7
                    break

    def _query_lines(self, options, prefix_to_match=None, forced_account_id=None):
        """
        This function is overridden to format and add the new account data (code and name) to the line dictionary.
        """
        lines = []
        asset_lines = self._query_values(options, prefix_to_match=prefix_to_match, forced_account_id=forced_account_id)

        parent_lines = []
        children_lines = defaultdict(list)
        for al in asset_lines:
            if al['parent_id']:
                children_lines[al['parent_id']].append(al)
            else:
                parent_lines.append(al)

        for al in parent_lines:
            asset_children_lines = children_lines[al['asset_id']]
            asset_parent_values = self._get_parent_asset_values(options, al, asset_children_lines)

            # ==================== START OF MODIFICATION (CODE + NAME) ====================
            # Format the account string to include both code and name
            fixed_account_display = f"{al.get('fixed_asset_account_code', '')} {al.get('fixed_asset_account_name', '')}".strip()
            depreciation_account_display = f"{al.get('depreciation_account_code', '')} {al.get('depreciation_account_name', '')}".strip()
            expense_account_display = f"{al.get('expense_account_code', '')} {al.get('expense_account_name', '')}".strip()
            # ===================== END OF MODIFICATION (CODE + NAME) =====================

            columns_by_expr_label = {
                "acquisition_date": al["asset_acquisition_date"] and format_date(self.env, al["asset_acquisition_date"]) or "",
                "first_depreciation": al["asset_date"] and format_date(self.env, al["asset_date"]) or "",
                "method": (al["asset_method"] == "linear" and _("Linear")) or (al["asset_method"] == "degressive" and _("Declining")) or _("Dec. then Straight"),
                "fixed_asset_account": fixed_account_display,
                "depreciation_account": depreciation_account_display,
                "expense_account": expense_account_display,
                **asset_parent_values
            }

            lines.append((al['account_id'], al['asset_id'], al['asset_group_id'], columns_by_expr_label))
        return lines

    def _get_parent_asset_values(self, options, asset_line, asset_children_lines):
        """
        This function contains the previous modification for dates. It remains unchanged.
        """
        res = super(AssetsReportCustomHandler, self)._get_parent_asset_values(options, asset_line, asset_children_lines)

        asset = self.env['account.asset'].browse(asset_line['asset_id'])
        date_from = fields.Date.to_date(options['date']['date_from'])
        date_to = fields.Date.to_date(options['date']['date_to'])

        asset_opening = 0.0
        asset_add = 0.0

        all_asset_ids = [asset.id] + [child['asset_id'] for child in asset_children_lines]
        
        related_move_lines = self.env['account.move.line'].search([
            ('asset_ids', 'in', all_asset_ids),
            ('move_id.state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_fixed')
        ])

        if related_move_lines:
            for line in related_move_lines:
                line_value = line.balance
                if line.date < date_from:
                    asset_opening += line_value
                elif date_from <= line.date <= date_to:
                    asset_add += line_value
            
            res['assets_date_from'] = asset_opening
            res['assets_plus'] = asset_add
            asset_closing = asset_opening + asset_add - res.get('assets_minus', 0.0)
            res['assets_date_to'] = asset_closing
            res['balance'] = asset_closing - res.get('depre_date_to', 0.0)

        return res

    def _query_values(self, options, prefix_to_match=None, forced_account_id=None):
        """
        This function is overridden to modify the SQL query to fetch both code and name for the new account fields.
        """
        self.env['account.move.line'].check_access('read')
        self.env['account.asset'].check_access('read')

        query = Query(self.env, alias='asset', table=SQL.identifier('account_asset'))
        
        fixed_account_alias = query.join(lhs_alias='asset', lhs_column='account_asset_id', rhs_table='account_account', rhs_column='id', link='account_asset_id')
        depre_account_alias = query.join(lhs_alias='asset', lhs_column='account_depreciation_id', rhs_table='account_account', rhs_column='id', link='account_depreciation_id')
        expense_account_alias = query.join(lhs_alias='asset', lhs_column='account_depreciation_expense_id', rhs_table='account_account', rhs_column='id', link='account_depreciation_expense_id')
        
        # ==================== START OF MODIFICATION (SQL: CODE + NAME) ====================
        # Define SQL expressions to get both the account code and name
        fixed_asset_account_code = self.env['account.account']._field_to_sql(fixed_account_alias, 'code', query)
        fixed_asset_account_name = self.env['account.account']._field_to_sql(fixed_account_alias, 'name', query)
        
        depreciation_account_code = self.env['account.account']._field_to_sql(depre_account_alias, 'code', query)
        depreciation_account_name = self.env['account.account']._field_to_sql(depre_account_alias, 'name', query)

        expense_account_code = self.env['account.account']._field_to_sql(expense_account_alias, 'code', query)
        expense_account_name = self.env['account.account']._field_to_sql(expense_account_alias, 'name', query)
        # ===================== END OF MODIFICATION (SQL: CODE + NAME) =====================

        query.add_join('LEFT JOIN', alias='move', table='account_move', condition=SQL(f"""
            move.asset_id = asset.id AND move.state {"!= 'cancel'" if options.get('all_entries') else "= 'posted'"}
        """))

        account_id = SQL.identifier(fixed_account_alias, 'id')

        if prefix_to_match:
            query.add_where(SQL("asset.name ILIKE %s", f"{prefix_to_match}%"))
        if forced_account_id:
            query.add_where(SQL("%s = %s", account_id, forced_account_id))

        # ... (rest of the function is the same)
        analytic_account_ids = []
        if options.get('analytic_accounts') and not any(x in options.get('analytic_accounts_list', []) for x in options['analytic_accounts']):
            analytic_account_ids += [[str(acc_id) for acc_id in options['analytic_accounts']]]
        if options.get('analytic_accounts_list'):
            analytic_account_ids += [[str(acc_id) for acc_id in options.get('analytic_accounts_list')]]
        if analytic_account_ids:
            query.add_where(SQL('%s && %s', analytic_account_ids, self.env['account.asset']._query_analytic_accounts('asset')))

        selected_journals = tuple(journal['id'] for journal in options.get('journals', []) if journal['model'] == 'account.journal' and journal['selected'])
        if selected_journals:
            query.add_where(SQL("asset.journal_id in %s", selected_journals))

        sql = SQL(
            """
            SELECT asset.id AS asset_id,
                   asset.parent_id AS parent_id,
                   asset.name AS asset_name,
                   asset.asset_group_id AS asset_group_id,
                   asset.original_value AS asset_original_value,
                   asset.currency_id AS asset_currency_id,
                   COALESCE(asset.salvage_value, 0) as asset_salvage_value,
                   MIN(move.date) AS asset_date,
                   asset.disposal_date AS asset_disposal_date,
                   asset.acquisition_date AS asset_acquisition_date,
                   asset.method AS asset_method,
                   asset.method_number AS asset_method_number,
                   asset.method_period AS asset_method_period,
                   asset.method_progress_factor AS asset_method_progress_factor,
                   asset.state AS asset_state,
                   asset.company_id AS company_id,
                   %(account_id)s AS account_id,
                   -- New fields (code and name) added to SELECT statement
                   %(fixed_asset_account_code)s AS fixed_asset_account_code,
                   %(fixed_asset_account_name)s AS fixed_asset_account_name,
                   %(depreciation_account_code)s AS depreciation_account_code,
                   %(depreciation_account_name)s AS depreciation_account_name,
                   %(expense_account_code)s AS expense_account_code,
                   %(expense_account_name)s AS expense_account_name,
                   COALESCE(SUM(move.depreciation_value) FILTER (WHERE move.date < %(date_from)s), 0) + COALESCE(asset.already_depreciated_amount_import, 0) AS depreciated_before,
                   COALESCE(SUM(move.depreciation_value) FILTER (WHERE move.date BETWEEN %(date_from)s AND %(date_to)s), 0) AS depreciated_during,
                   COALESCE(SUM(move.depreciation_value) FILTER (WHERE move.date BETWEEN %(date_from)s AND %(date_to)s AND move.asset_number_days IS NULL), 0) AS asset_disposal_value
              FROM %(from_clause)s
             WHERE %(where_clause)s
               AND asset.company_id in %(company_ids)s
               AND (asset.acquisition_date <= %(date_to)s OR move.date <= %(date_to)s)
               AND (asset.disposal_date >= %(date_from)s OR asset.disposal_date IS NULL)
               AND (asset.state not in ('model', 'draft', 'cancelled') OR (asset.state = 'draft' AND %(include_draft)s))
               AND asset.active = 't'
          GROUP BY asset.id, account_id, fixed_asset_account_code, fixed_asset_account_name, depreciation_account_code, depreciation_account_name, expense_account_code, expense_account_name
          ORDER BY account_id, asset.acquisition_date, asset.id;
            """,
            account_id=account_id,
            date_from=options['date']['date_from'],
            date_to=options['date']['date_to'],
            from_clause=query.from_clause,
            where_clause=query.where_clause or SQL('TRUE'),
            company_ids=tuple(self.env['account.report'].get_report_company_ids(options)),
            include_draft=options.get('all_entries', False),
            # Pass new SQL expressions (code and name) to the query
            fixed_asset_account_code=fixed_asset_account_code,
            fixed_asset_account_name=fixed_asset_account_name,
            depreciation_account_code=depreciation_account_code,
            depreciation_account_name=depreciation_account_name,
            expense_account_code=expense_account_code,
            expense_account_name=expense_account_name,
        )

        self._cr.execute(sql)
        results = self._cr.dictfetchall()
        return results


# ... (الكود السابق للموديول يبقى كما هو) ...

# ==================== START OF LANDSCAPE PDF FIX (PYTHON + CUSTOM PAPERFORMAT) ====================

class AccountReport(models.Model):
    _inherit = 'account.report'

    def _get_report_paperformat(self, options):
        """
        This function is overridden to return a custom landscape paper format
        with smaller margins specifically for the Depreciation Schedule report.
        """
        if self.id == self.env.ref('account_asset.account_asset_report').id:
            # Check if our custom paper format already exists
            paperformat = self.env.ref('custom_asset_report_dates.paperformat_asset_report_landscape_custom', raise_if_not_found=False)
            if not paperformat:
                # If it doesn't exist, create it
                paperformat = self.env['report.paperformat'].create({
                    'name': 'Depreciation Schedule Landscape (Custom)',
                    'format': 'A4',
                    'orientation': 'Landscape',
                    'margin_top': 25,
                    'margin_bottom': 20,
                    'margin_left': 5,   # Reduced from 7
                    'margin_right': 5,  # Reduced from 7
                    'header_line': False,
                    'header_spacing': 20,
                    'dpi': 90,
                })
                # Create an XML ID for it so we can reference it next time
                self.env['ir.model.data'].create({
                    'name': 'paperformat_asset_report_landscape_custom',
                    'module': 'custom_asset_report_dates',
                    'res_id': paperformat.id,
                    'model': 'report.paperformat',
                })
            return paperformat
        
        # For all other reports, call the original function.
        return super()._get_report_paperformat(options)

# ===================== END OF LANDSCAPE PDF FIX (PYTHON + CUSTOM PAPERFORMAT) =====================
