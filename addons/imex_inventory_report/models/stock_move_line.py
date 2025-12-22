# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # Frozen fields for main product qty and UoM
    main_product_qty = fields.Float(
        string="Main Product Quantity",
        digits="Product Unit of Measure",
        store=True,
        compute="_compute_main_product_qty",
    )
    main_product_uom_id = fields.Many2one(
        "uom.uom",
        string="Main Product UoM",
        store=True,
        compute="_compute_main_product_qty",
    )

    # 🔥 New fields
    is_internal_transfer = fields.Boolean(
        string="Internal Transfer",
        store=True,
        compute="_compute_internal_transfer_data",
    )
    internal_transfer_cost = fields.Float(
        string="Internal Transfer Cost",
        store=True,
        compute="_compute_internal_transfer_data",
    )

    # ---------------------------------------------------------------------
    # MAIN PRODUCT QUANTITY COMPUTE
    # ---------------------------------------------------------------------
    @api.depends(
        "move_id.state",
        "move_id.stock_valuation_layer_ids",
        "qty_done",
        "product_id",
        "product_uom_id",
    )
    def _compute_main_product_qty(self):
        """
        Compute quantity in the product’s base UoM (“main” quantity).
        Priority:
          1 If the move is 'done' and has valuation layers (SVL):
              - Use SVL.quantity (in product’s base UoM, historically accurate)
              - Distribute proportionally across move lines by qty_done
          2 Otherwise:
              - Fallback to live conversion using current UoM ratios
        """
        for line in self:
            if not line.product_id or not line.product_uom_id:
                line.main_product_qty = 0.0
                line.main_product_uom_id = False
                continue

            product = line.product_id
            target_uom = (
                product.sub_product_created.uom_id
                if product.sub_product_created
                else product.product_tmpl_id.uom_id
            )

            move = line.move_id
            main_qty = 0.0

            # ✅ Case 1: move is done and has valuation data
            if move.state == "done" and move.stock_valuation_layer_ids:
                svls = move.stock_valuation_layer_ids.filtered(
                    lambda svl: svl.product_id == product
                )

                if svls:
                    total_svl_qty = sum(svls.mapped("quantity"))
                    total_line_qty = sum(
                        move.move_line_ids.filtered(
                            lambda l: l.product_id == product
                        ).mapped("qty_done")
                    )

                    if total_line_qty:
                        proportion = line.qty_done / total_line_qty
                        main_qty = total_svl_qty * proportion
                    else:
                        main_qty = 0.0
                else:
                    # Fallback if SVL not available for this product
                    main_qty = line.product_uom_id._compute_quantity(
                        line.qty_done, target_uom, round=False
                    )

            else:
                # Case 2: fallback for draft/unvalued moves
                main_qty = line.product_uom_id._compute_quantity(
                    line.qty_done, target_uom, round=False
                )

            line.main_product_qty = abs(main_qty)
            line.main_product_uom_id = target_uom

    # ---------------------------------------------------------------------
    # INTERNAL TRANSFER COMPUTE
    # ---------------------------------------------------------------------
    @api.depends(
        "location_id.usage",
        "location_dest_id.usage",
        "main_product_qty",
        "product_id.standard_price",
    )
    def _compute_internal_transfer_data(self):
        """
        Detect and evaluate internal transfers:
          - If source and destination are internal → mark as internal transfer
          - Internal cost derived from main product cost (standard_price)
        """
        for line in self:
            is_internal = (
                    line.location_id.usage == "internal"
                    and line.location_dest_id.usage == "internal"
            )
            line.is_internal_transfer = is_internal

            if not is_internal or not line.product_id:
                line.internal_transfer_cost = 0.0
                continue

            # Determine main product reference (handle sub-products)
            if line.product_id.sub_product_created:
                main_product = line.product_id.sub_product_created
            else:
                main_product = line.product_id

            # Assign cost (based on product's base valuation)
            line.internal_transfer_cost = main_product.standard_price
