from odoo import api, fields, models, tools
from odoo.tools.safe_eval import safe_eval


class ImexInventoryReport(models.Model):
    _name = "imex.inventory.report"
    _description = "Imex Inventory Report"
    _auto = False

    company_id = fields.Many2one(comodel_name='res.company', default=lambda self: self.env.company)
    company_currency_id = fields.Many2one('res.currency', 'Currency', related='company_id.currency_id', readonly=True)
    product_id = fields.Many2one(comodel_name="product.product", readonly=True)
    product_barcode = fields.Char(related="product_id.barcode")
    product_default_code = fields.Char(related="product_id.default_code")
    product_uom_id = fields.Many2one(comodel_name="uom.uom", readonly=True)
    product_category = fields.Many2one(comodel_name="product.category", readonly=True)
    location = fields.Many2one(comodel_name="stock.location", readonly=True)
    initial = fields.Float(readonly=True)
    initial_amount = fields.Monetary(readonly=True,currency_field='company_currency_id')
    product_in = fields.Float(readonly=True)
    product_in_amount = fields.Monetary(readonly=True,currency_field='company_currency_id')
    product_out = fields.Float(readonly=True)
    product_out_amount = fields.Monetary(readonly=True,currency_field='company_currency_id')
    balance = fields.Float(readonly=True)
    amount = fields.Monetary(readonly=True,currency_field='company_currency_id')
    product_list_price = fields.Float( 'Sales Price', digits='Product Price', related="product_id.list_price", help="Price at which the product is sold to customers.")
    product_standard_price = fields.Float( 'Cost', digits='Product Price', related="product_id.standard_price", help="Value of the product (automatically computed in AVCO)")
    line_value = fields.Float("Value", compute='_compute_value')

    def _compute_value(self):
        for rec in self:
            rec.line_value = rec.product_standard_price * rec.balance

    def _get_locations(self, location_id, is_groupby_location):
        count_internal_transfer = True
        if location_id:
            if is_groupby_location:
                locations = tuple(
                    self.env["stock.location"]
                    .search([("id", "child_of", location_id.ids)])
                    .ids
                )
            else:
                locations = tuple(location_id.ids)
        else:
            locations = tuple(
                self.env["stock.location"].search([("usage", "=", "internal")]).ids
            )
            if not locations:
                locations = (-1,)
            if not is_groupby_location:
                count_internal_transfer = False
        return locations, count_internal_transfer

    def _get_product_category_ids(self, product_category_ids):
        if product_category_ids:
            product_category_ids = tuple(
                self.env["product.category"]
                .search([("id", "child_of", product_category_ids.ids)])
                .ids
            )
        else:
            product_category_ids = tuple(self.env["product.category"].search([]).ids)
            if not product_category_ids:
                product_category_ids = (-1,)
        return product_category_ids

    def _get_product_ids(self, product_ids, product_category_ids):
        if product_ids:
            product_ids = tuple(product_ids.ids)
        elif product_category_ids:
            product_ids = tuple(
                self.env["product.product"]
                .search([("categ_id", "child_of", product_category_ids.ids)])
                .ids
            )
            if not product_ids:
                product_ids = (-1,)
        else:
            product_ids = tuple(
                self.env["product.product"].search([("active", "=", True)]).ids
            )
            if not product_ids:
                product_ids = (-1,)
        return product_ids

    def _get_internal_picking_type(self, is_groupby_location):
        internal_picking_type = None
        if not is_groupby_location:
            internal_picking_type = tuple(
                self.env["stock.picking.type"].search([("code", "=", "internal")]).ids
            )
            if not internal_picking_type:
                internal_picking_type = (-1,)
        return internal_picking_type

    def init_results(self, filter_fields):
        date_from = filter_fields.date_from or "1900-01-01"
        date_to = filter_fields.date_to or fields.Date.context_today(self)
        is_groupby_location = filter_fields.is_groupby_location
        allowed_company_ids = tuple(self._context.get("allowed_company_ids", []))
        if not allowed_company_ids:
            allowed_company_ids = (-1,)  # fallback if no allowed companies

        locations, count_internal_transfer = self._get_locations(
            filter_fields.location_id, is_groupby_location
        )
        product_category_ids = self._get_product_category_ids(
            filter_fields.product_category_ids
        )
        product_ids = self._get_product_ids(
            filter_fields.product_ids, filter_fields.product_category_ids
        )

        if count_internal_transfer:
            query_ = """SELECT *,
           (a.initial + a.product_in - a.product_out) AS balance,
           (a.initial_amount + a.product_in_amount - a.product_out_amount) AS amount
    FROM (
        SELECT ROW_NUMBER() OVER () AS id,
               move_group_location.product_id,
               move_group_location.main_product_uom_id AS product_uom_id,
               move_group_location.location,
               move_group_location.product_category,
               move_group_location.company_id,

               (SUM(CASE WHEN CAST(move_group_location.date AS date) < %s
                              AND move_group_location.location = move_group_location.location_dest_id
                         THEN move_group_location.main_product_qty ELSE 0 END)
                -
                SUM(CASE WHEN CAST(move_group_location.date AS date) < %s
                              AND move_group_location.location = move_group_location.location_id
                         THEN move_group_location.main_product_qty ELSE 0 END)) AS initial,

               (SUM(CASE WHEN CAST(move_group_location.date AS date) < %s
                              AND move_group_location.location = move_group_location.location_dest_id
                         THEN move_group_location.main_product_qty * move_group_location.unit_cost ELSE 0 END)
                -
                SUM(CASE WHEN CAST(move_group_location.date AS date) < %s
                              AND move_group_location.location = move_group_location.location_id
                         THEN move_group_location.main_product_qty * move_group_location.unit_cost ELSE 0 END)) AS initial_amount,

               SUM(CASE WHEN CAST(move_group_location.date AS date) >= %s
                            AND move_group_location.location = move_group_location.location_dest_id
                       THEN move_group_location.main_product_qty ELSE 0 END) AS product_in,

               SUM(CASE WHEN CAST(move_group_location.date AS date) >= %s
                            AND move_group_location.location = move_group_location.location_dest_id
                       THEN move_group_location.main_product_qty * move_group_location.unit_cost ELSE 0 END) AS product_in_amount,

               SUM(CASE WHEN CAST(move_group_location.date AS date) >= %s
                            AND move_group_location.location = move_group_location.location_id
                       THEN move_group_location.main_product_qty ELSE 0 END) AS product_out,

               SUM(CASE WHEN CAST(move_group_location.date AS date) >= %s
                            AND move_group_location.location = move_group_location.location_id
                       THEN move_group_location.main_product_qty * move_group_location.unit_cost ELSE 0 END) AS product_out_amount

        FROM (
            WITH svl_avg AS (
                SELECT
                    stock_move_id,
                    SUM(value) AS total_value,
                    SUM(quantity) FILTER (WHERE quantity != 0) AS total_qty,
                    CASE
                        WHEN SUM(quantity) != 0 THEN SUM(value) / SUM(quantity)
                        ELSE 0
                    END AS avg_cost
                FROM stock_valuation_layer
                GROUP BY stock_move_id
            )

            -- OUTGOING
            SELECT sm.id,
                   sm.company_id,
                   move_line.date,
                   move_line.product_id,
                   move_line.main_product_uom_id,
                   move_line.location_id AS location,
                   move_line.location_id,
                   move_line.location_dest_id,
                   template.categ_id AS product_category,
                   move_line.main_product_qty,
                   CASE WHEN move_line.is_internal_transfer THEN COALESCE(move_line.internal_transfer_cost, 0)
                   ELSE COALESCE(svl.avg_cost, 0)
                   END AS unit_cost
            FROM stock_move_line AS move_line
            LEFT JOIN svl_avg svl
                   ON move_line.move_id = svl.stock_move_id
            JOIN stock_location AS location_src
                 ON move_line.location_id = location_src.id
            JOIN stock_move AS sm
                 ON move_line.move_id = sm.id
            JOIN product_product AS product
                 ON move_line.product_id = product.id
            JOIN product_template AS template
                 ON product.product_tmpl_id = template.id
            WHERE move_line.location_id IN %s
              AND move_line.state = 'done'
              AND move_line.product_id IN %s
              AND template.categ_id IN %s
              AND CAST(move_line.date AS date) <= %s
              AND location_src.usage = 'internal'
              AND template.type = 'consu'
              AND (sm.company_id IN %s OR sm.company_id IS NULL)

            UNION ALL

            -- INCOMING
            SELECT sm.id,
                   sm.company_id,
                   move_line.date,
                   move_line.product_id,
                   move_line.main_product_uom_id,
                   move_line.location_dest_id AS location,
                   move_line.location_id,
                   move_line.location_dest_id,
                   template.categ_id AS product_category,
                   move_line.main_product_qty,
                   CASE WHEN move_line.is_internal_transfer THEN COALESCE(move_line.internal_transfer_cost, 0)
                   ELSE COALESCE(svl.avg_cost, 0)
                   END AS unit_cost
            FROM stock_move_line AS move_line
            LEFT JOIN svl_avg svl
                   ON move_line.move_id = svl.stock_move_id
            JOIN stock_location AS location_dest
                 ON move_line.location_dest_id = location_dest.id
            JOIN stock_move AS sm
                 ON move_line.move_id = sm.id
            JOIN product_product AS product
                 ON move_line.product_id = product.id
            JOIN product_template AS template
                 ON product.product_tmpl_id = template.id
            WHERE move_line.location_dest_id IN %s
              AND move_line.state = 'done'
              AND move_line.product_id IN %s
              AND template.categ_id IN %s
              AND CAST(move_line.date AS date) <= %s
              AND location_dest.usage = 'internal'
              AND template.type = 'consu'
              AND (sm.company_id IN %s OR sm.company_id IS NULL)
        ) AS move_group_location
        GROUP BY move_group_location.product_id,
                 move_group_location.main_product_uom_id,
                 move_group_location.location,
                 move_group_location.product_category,
                 move_group_location.company_id
        ORDER BY move_group_location.product_id,
                 move_group_location.main_product_uom_id,
                 move_group_location.location,
                 move_group_location.product_category,
                 move_group_location.company_id
    ) AS a
    """
            params = (
                date_from, date_from, date_from, date_from,
                date_from, date_from, date_from, date_from,
                locations, product_ids, product_category_ids, date_to, allowed_company_ids,
                locations, product_ids, product_category_ids, date_to, allowed_company_ids,
            )

        else:
            query_ = """SELECT *,
                   (a.initial + a.product_in - a.product_out) AS balance,
                   (a.initial_amount + a.product_in_amount - a.product_out_amount) AS amount
            FROM (
                SELECT ROW_NUMBER() OVER () AS id,
                       move_group.product_id,
                       move_group.main_product_uom_id AS product_uom_id,
                       NULL AS location,
                       move_group.product_category,
                       move_group.company_id,   

                       (SUM(CASE WHEN CAST(move_group.date AS date) < %s
                                      AND move_group.location = move_group.location_dest_id
                                 THEN move_group.main_product_qty ELSE 0 END)
                        -
                        SUM(CASE WHEN CAST(move_group.date AS date) < %s
                                      AND move_group.location = move_group.location_id
                                 THEN move_group.main_product_qty ELSE 0 END)
                       ) AS initial,

                       (SUM(CASE WHEN CAST(move_group.date AS date) < %s
                                      AND move_group.location = move_group.location_dest_id
                                 THEN move_group.main_product_qty * move_group.avg_cost ELSE 0 END)
                        -
                        SUM(CASE WHEN CAST(move_group.date AS date) < %s
                                      AND move_group.location = move_group.location_id
                                 THEN move_group.main_product_qty * move_group.avg_cost ELSE 0 END)
                       ) AS initial_amount,

                       SUM(CASE WHEN CAST(move_group.date AS date) >= %s
                                    AND move_group.location = move_group.location_dest_id
                               THEN move_group.main_product_qty ELSE 0 END) AS product_in,

                       SUM(CASE WHEN CAST(move_group.date AS date) >= %s
                                    AND move_group.location = move_group.location_dest_id
                               THEN move_group.main_product_qty * move_group.avg_cost ELSE 0 END) AS product_in_amount,

                       SUM(CASE WHEN CAST(move_group.date AS date) >= %s
                                    AND move_group.location = move_group.location_id
                               THEN move_group.main_product_qty ELSE 0 END) AS product_out,

                       SUM(CASE WHEN CAST(move_group.date AS date) >= %s
                                    AND move_group.location = move_group.location_id
                               THEN move_group.main_product_qty * move_group.avg_cost ELSE 0 END) AS product_out_amount

                FROM (
                    WITH svl_avg AS (
                        SELECT
                            stock_move_id,
                            SUM(value) AS total_value,
                            SUM(quantity) FILTER (WHERE quantity != 0) AS total_qty,
                            CASE
                                WHEN SUM(quantity) != 0 THEN SUM(value) / SUM(quantity)
                                ELSE 0
                            END AS avg_cost
                        FROM stock_valuation_layer
                        GROUP BY stock_move_id
                    )
                    -- OUTGOING
                    SELECT sm.id,
                           sm.company_id,
                           move_line.date,
                           move_line.product_id,
                           move_line.main_product_uom_id,
                           move_line.location_id AS location,
                           move_line.location_id,
                           move_line.location_dest_id,
                           template.categ_id AS product_category,
                           move_line.main_product_qty,
                           COALESCE(svl.avg_cost, 0) AS avg_cost
                    FROM stock_move_line AS move_line
                    LEFT JOIN svl_avg svl
                           ON move_line.move_id = svl.stock_move_id
                    JOIN stock_location AS location_src
                         ON move_line.location_id = location_src.id
                    JOIN stock_move AS sm
                         ON move_line.move_id = sm.id
                    JOIN product_product AS product
                         ON move_line.product_id = product.id
                    JOIN product_template AS template
                         ON product.product_tmpl_id = template.id
                    WHERE (move_line.location_id IN %s OR move_line.location_dest_id IN %s)
                      AND move_line.state = 'done'
                      AND move_line.product_id IN %s
                      AND template.categ_id IN %s
                      AND CAST(move_line.date AS date) <= %s
                      AND (location_src.usage = 'internal' OR location_src.usage IS NULL)
                      AND template.type = 'consu'
                      AND (sm.company_id IN %s OR sm.company_id IS NULL)

                    UNION ALL

                    -- INCOMING
                    SELECT sm.id,
                           sm.company_id,
                           move_line.date,
                           move_line.product_id,
                           move_line.main_product_uom_id,
                           move_line.location_dest_id AS location,
                           move_line.location_id,
                           move_line.location_dest_id,
                           template.categ_id AS product_category,
                           move_line.main_product_qty,
                           COALESCE(svl.avg_cost, 0) AS avg_cost
                    FROM stock_move_line AS move_line
                    LEFT JOIN svl_avg svl
                           ON move_line.move_id = svl.stock_move_id
                    JOIN stock_location AS location_dest
                         ON move_line.location_dest_id = location_dest.id
                    JOIN stock_move AS sm
                         ON move_line.move_id = sm.id
                    JOIN product_product AS product
                         ON move_line.product_id = product.id
                    JOIN product_template AS template
                         ON product.product_tmpl_id = template.id
                    WHERE (move_line.location_id IN %s OR move_line.location_dest_id IN %s)
                      AND move_line.state = 'done'
                      AND move_line.product_id IN %s
                      AND template.categ_id IN %s
                      AND CAST(move_line.date AS date) <= %s
                      AND (location_dest.usage = 'internal' OR location_dest.usage IS NULL)
                      AND template.type = 'consu'
                      AND (sm.company_id IN %s OR sm.company_id IS NULL)
                ) AS move_group
                GROUP BY move_group.product_id,
                         move_group.main_product_uom_id,
                         move_group.product_category,
                         move_group.company_id
                ORDER BY move_group.product_id,
                         move_group.company_id
            ) AS a
            """
            params = (
                date_from,
                date_from,
                date_from,
                date_from,
                date_from,
                date_from,
                date_from,
                date_from,

                locations,
                locations,
                product_ids,
                product_category_ids,
                date_to,
                allowed_company_ids,

                locations,
                locations,
                product_ids,
                product_category_ids,
                date_to,
                allowed_company_ids,
            )

        tools.drop_view_if_exists(self._cr, self._table)
        res = self._cr.execute(
            """CREATE VIEW {} as ({})""".format(self._table, query_), params
        )
        return res

    def report_details(self):
        filters = self._context.get("filters") or {}
        filters["product_ids"] = [(6, 0, self.product_id.ids)]
        filters["location_id"] = filters.get("location_id", False) or self.location.id
        return self.env["imex.inventory.details.report"].view_report_details(filters)

    def button_tree_view(self):
        filters = self._context.get("filters") or {}
        filters["product_ids"] = [(6, 0, self.product_id.ids)]
        filters["location_id"] = filters.get("location_id",False) or self.location.id
        report = self.env["imex.inventory.report.wizard"].create(filters)
        self.env["imex.inventory.details.report"].init_results(report)
        details = self.env["imex.inventory.details.report"].search([])
        context = self._context.copy()
        context["active_ids"] = details.ids
        data = {
            "product_default_code": report.product_ids.default_code,
            "product_name": report.product_ids.name,
            "date_from": report.date_from or None,
            "date_to": report.date_to or fields.Date.context_today(self),
            "location": report.location_id.complete_name or None,
            "category": report.product_ids.categ_id.complete_name or None,
        }
        context["data"] = data
        return {
            "name": "Imex Inventory Details Report",
            "view_mode": "list",
            "res_model": "imex.inventory.details.report",
            "type": "ir.actions.act_window",
            "context": context,
        }