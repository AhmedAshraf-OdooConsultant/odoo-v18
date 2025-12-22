from odoo import api, fields, models, tools
from odoo.tools import json_default
import io

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


class ImexInventoryDetailsReport(models.Model):
    _name = "imex.inventory.details.report"
    _description = "Imex Inventory Details Report"
    _order = "date asc"
    _auto = False

    date = fields.Datetime(readonly=True)
    product_id = fields.Many2one(comodel_name="product.product", readonly=True)
    product_barcode = fields.Char(related="product_id.barcode")
    product_default_code = fields.Char(related="product_id.default_code")
    quantity = fields.Float(readonly=True)
    product_uom_id = fields.Many2one( comodel_name="uom.uom", readonly=True)
    product_category = fields.Many2one( comodel_name="product.category", readonly=True)
    unit_cost = fields.Float( readonly=True, digits="Product Price")
    reference = fields.Char( readonly=True)
    partner_id = fields.Many2one( comodel_name="res.partner", readonly=True)
    origin = fields.Char( readonly=True)
    location_id = fields.Many2one( comodel_name="stock.location", readonly=True)
    location_dest_id = fields.Many2one( comodel_name="stock.location", readonly=True)
    initial = fields.Float( readonly=True)
    initial_amount = fields.Monetary( readonly=True)
    product_in = fields.Float( readonly=True)
    product_out = fields.Float( readonly=True)
    picking_id = fields.Many2one( comodel_name="stock.picking", readonly=True)
    product_balance = fields.Float( compute="_compute_product_balance_amount", string="Balance")
    product_amount = fields.Monetary( compute="_compute_product_balance_amount", string="Amount")
    main_product_uom_id = fields.Many2one( comodel_name="uom.uom", string="Product UoM", readonly=True)
    company_id = fields.Many2one( comodel_name="res.company", default=lambda self: self.env.company.id)
    currency_id = fields.Many2one("res.currency", "Currency", related="company_id.currency_id",readonly=True, required=True)
    transaction_value = fields.Monetary(string="Transaction Value", compute="_compute_transaction_value", readonly=True)
    display_name = fields.Char(string="Display Name", compute="_compute_display_name", store=False)

    @api.depends('reference', 'picking_id.origin')
    def _compute_display_name(self):
        for rec in self:
            name = rec.reference or "Initial"
            if rec.picking_id and rec.picking_id.origin:
                name = "{} ({})".format(name, rec.picking_id.origin)
            rec.display_name = name

    @api.depends("product_in", "product_out", "unit_cost")
    def _compute_transaction_value(self):
        for record in self:
            in_qty = record.product_in or 0.0
            out_qty = record.product_out or 0.0
            record.transaction_value = (in_qty - out_qty) * (record.unit_cost or 0.0)

    @api.depends("initial_amount", "initial", "product_in", "product_out", "unit_cost", "product_id")
    def _compute_product_balance_amount(self):
        for record in self:
            # Find previous movement of the same product
            if record.product_id:
                previous_record = self.filtered(
                    lambda rec: rec.product_id.id == record.product_id.id and rec.id < record.id
                ).sorted("id", reverse=True)[:1] or self.filtered(
                    lambda rec: not rec.product_id and rec.id < record.id
                )
            else:
                previous_record = False
            if previous_record:
                # Normal movement line
                previous_product_balance = previous_record.product_balance
                previous_product_amount = previous_record.product_amount
            else:
                # Initial line → use initial fields instead of product_in/out
                previous_product_balance = record.initial or 0.0
                previous_product_amount = record.initial_amount or 0.0
            # Compute new cumulative values
            record.product_balance = previous_product_balance + (record.product_in - record.product_out)
            record.product_amount = previous_product_amount + (
                    record.product_in * record.unit_cost - record.product_out * record.unit_cost
            )

    def _get_locations(self, location_id, is_groupby_location):
        if location_id:
            if is_groupby_location:
                locations = tuple(
                    self.env["stock.location"].search([("id", "child_of", location_id.ids)]).ids
                )
            else:
                locations = tuple(location_id.ids)
        else:
            locations = tuple(
                self.env["stock.location"].search([("usage", "=", "internal")]).ids
            )
            if not locations:
                locations = (-1,)
        return locations

    def action_ref_picking(self):
        self.ensure_one()
        source = self.picking_id
        if source and source.check_access_rights("read", raise_exception=False):
            return {
                "name": "Picking",
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "views": [[False, "form"]],
                "res_id": self.picking_id.id,
            }
        return

    def init_results(self, filter_fields):
        date_from = filter_fields.date_from or "1900-01-01"
        date_to = filter_fields.date_to or fields.Date.context_today(self)
        is_groupby_location = filter_fields.is_groupby_location

        locations = list(self._get_locations(filter_fields.location_id, is_groupby_location)) or [-1]
        product_ids = filter_fields.product_ids.ids or [-1]
        allowed_company_ids = tuple(self._context.get("allowed_company_ids", [])) or (-1,)
        current_company_id = self.env.company.id  # Ensure a fallback company

        query_ = """
        SELECT row_number() OVER () AS id, * FROM (
            WITH svl AS (
                SELECT 
                    stock_move_id,
                    unit_cost,
                    value
                FROM stock_valuation_layer
            )

            -- Initial balance row
            SELECT 
                SUM(CASE WHEN move.location_dest_id = ANY(%s) THEN move.main_product_qty ELSE 0 END)
              - SUM(CASE WHEN move.location_id = ANY(%s) THEN move.main_product_qty ELSE 0 END) AS initial,
                SUM(CASE WHEN move.location_dest_id = ANY(%s) THEN move.main_product_qty * CASE WHEN move.is_internal_transfer THEN COALESCE(move.internal_transfer_cost, 0) ELSE COALESCE(svl.unit_cost, 0) END ELSE 0 END)
              - SUM(CASE WHEN move.location_id = ANY(%s) THEN move.main_product_qty * CASE WHEN move.is_internal_transfer THEN COALESCE(move.internal_transfer_cost, 0) ELSE COALESCE(svl.unit_cost, 0) END ELSE 0 END) AS initial_amount,
                NULL::timestamp AS date,
                NULL::int AS product_id,
                NULL::float AS quantity,
                NULL::int AS product_uom_id,
                NULL::int AS product_category,
                0::float AS unit_cost,
                NULL::text AS reference,
                NULL::int AS partner_id,
                NULL::text AS origin,
                NULL::int AS location_id,
                NULL::int AS location_dest_id,
                NULL::float AS product_in,
                NULL::float AS product_out,
                NULL::int AS picking_id,
                NULL::int AS line_id,
                NULL::int AS main_product_uom_id,
                COALESCE(MIN(move.company_id), %s) AS company_id,
                0::float AS transaction_value
            FROM stock_move_line move
            LEFT JOIN svl ON move.move_id = svl.stock_move_id
            WHERE move.state = 'done'
              AND (move.company_id IN %s OR move.company_id IS NULL)
              AND (move.location_id = ANY(%s) OR move.location_dest_id = ANY(%s))
              AND move.product_id = ANY(%s)
              AND move.date::date < %s

            UNION ALL

            -- Movement lines
            SELECT
                NULL AS initial,
                NULL AS initial_amount,
                move.date,
                move.product_id,
                move.main_product_qty AS quantity,
                move.main_product_uom_id AS product_uom_id,
                template.categ_id AS product_category,
                CASE WHEN move.is_internal_transfer = TRUE
                     THEN COALESCE(move.internal_transfer_cost, 0)
                ELSE
                     COALESCE(svl.unit_cost, 0)
                END AS unit_cost,
                move.reference,
                s_p.partner_id,
                s_p.origin,
                move.location_id,
                move.location_dest_id,
                CASE WHEN move.location_dest_id = ANY(%s) THEN move.main_product_qty ELSE 0 END AS product_in,
                CASE WHEN move.location_id = ANY(%s) THEN move.main_product_qty ELSE 0 END AS product_out,
                move.picking_id,
                move.id AS line_id,
                template.uom_id AS main_product_uom_id,
                move.company_id AS company_id,
                COALESCE(svl.value, 0) AS transaction_value
            FROM stock_move_line move
            LEFT JOIN svl ON move.move_id = svl.stock_move_id
            LEFT JOIN product_product product ON move.product_id = product.id
            LEFT JOIN product_template template ON product.product_tmpl_id = template.id
            LEFT JOIN stock_picking s_p ON move.picking_id = s_p.id
            WHERE move.state = 'done'
              AND (move.company_id IN %s OR move.company_id IS NULL)
              AND (move.location_id = ANY(%s) OR move.location_dest_id = ANY(%s))
              AND move.product_id = ANY(%s)
              AND move.date::date BETWEEN %s AND %s
        ) AS report
        ORDER BY 
            CASE WHEN report.date IS NULL THEN 0 ELSE 1 END,
            report.date,
            report.reference
        """

        params = (
            locations,  # 1: initial row destination
            locations,  # 2: initial row source
            locations,  # 3: initial row destination
            locations,  # 4: initial row source
            current_company_id,  # 5: fallback company
            allowed_company_ids,  # 6: initial row company filter
            locations,  # 7: initial row location_id filter
            locations,  # 8: initial row location_dest_id filter
            product_ids,  # 9: initial row product filter
            date_from,  # 10: initial row date
            locations,  # 11: movement destination filter
            locations,  # 12: movement source filter
            allowed_company_ids,  # 13: movement company filter
            locations,  # 14: movement location_id filter
            locations,  # 15: movement location_dest_id filter
            product_ids,  # 16: movement product filter
            date_from,  # 17: movement start date
            date_to,  # 18: movement end date
        )

        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"CREATE VIEW {self._table} AS ({query_})", params)

    def view_report_details(self, filters):
        report = self.env["imex.inventory.report.wizard"].create(filters)
        self.env["imex.inventory.details.report"].init_results(report)
        details = self.env["imex.inventory.details.report"].search([])
        data = {
            "product_default_code": report.product_ids.default_code,
            "product_name": report.product_ids.name,
            "date_from": report.date_from or None,
            "date_to": report.date_to or fields.Date.context_today(self),
            "location": report.location_id.complete_name or None,
            "category": report.product_ids.categ_id.complete_name or None,
            "detail_ids": details.ids,
        }
        return (
            self.env.ref("imex_inventory_report.action_imex_inventory_details_report_html")
            .with_context(active_model="imex.inventory.details.report")
            .report_action(details.ids, data=data)
        )