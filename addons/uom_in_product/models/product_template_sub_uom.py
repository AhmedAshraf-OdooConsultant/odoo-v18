from odoo import models, fields, api
import collections
from odoo.tools.float_utils import float_round, float_is_zero


class ProductTemplateSubUom(models.Model):
    _inherit = 'product.template'

    create_other_units = fields.Boolean(string="Create Other Units")
    uom_cat_id = fields.Many2one(comodel_name='uom.category', compute="_compute_uom_cat_id")
    other_units_id = fields.Many2many(comodel_name='uom.uom')
    sub_product_created = fields.One2many(comodel_name='product.product', readonly=False,
                                          inverse_name='sub_product_created',
                                          compute='_compute_sub_product_created')

    def _assign_default_code(self):
        for rec in self:
            active = self.env['ir.config_parameter'].sudo().get_param('uom_in_product.set_uom_to_reference')
            print('active', active)
            if active:
                rec.default_code = rec.uom_id.name


    def get_sub_units_from_used_in_bom(self):
        print("get_sub_units_from_used_in_bom")
        records = self.search([])
        sub_product = self.search([('purchase_ok', '=', False)])
        main_product = records - sub_product
        for rec in main_product:
            for bom in self.env['mrp.bom'].search([('bom_line_ids.product_tmpl_id', '=', rec.id)]):
                rec.create_other_units = True
                rec._compute_sub_product_created()
                rec._compute_other_sub_units()

    def _compute_other_sub_units(self):
        for rec in self:
            for sub_product in rec.sub_product_created:
                rec.other_units_id += sub_product.uom_id

    @api.onchange('categ_id')
    def _onchange_uom_cat_id(self):
        for rec in self:
            for sub_product in rec.sub_product_created:
                print("sub_product", sub_product.ids)
                self.env['product.product'].search([('id', '=', sub_product.ids)]).write({'categ_id': rec.categ_id.id})


    @api.depends('uom_id')
    def _compute_sub_product_created(self):
        for rec in self:
            used_in_bom = self.env['mrp.bom'].search([('bom_line_ids.product_tmpl_id', '=',rec.id )])
            for bom in used_in_bom:
                rec.sub_product_created += self.env['product.product'].search([('categ_id', '=', rec.categ_id.id),('purchase_ok', '=', False), ('uom_id', '=', bom.product_tmpl_id.uom_id.id),('product_tmpl_id', '=', bom.product_tmpl_id.id)])

    @api.onchange('barcode')
    def onchange_barcode(self):
        for rec in self:
            if rec.purchase_ok:
                if rec.sub_product_created:
                    if len(rec.sub_product_created.ids) == 1:
                        rec.sub_product_created.barcode = f"{rec.barcode}-1" if rec.barcode else False
                    else:
                        i = 1
                        while self.check_barcode(i):
                            i += 1
                        for sub_product in rec.sub_product_created:
                            if not sub_product.barcode:
                                sub_product.barcode = f"{rec.barcode}-{i}"
                                i += 1
                            else:
                                if not rec.barcode:
                                    sub_product.barcode = False
                                else:
                                    sequence = sub_product.barcode.split("-")
                                    sub_product.barcode = f"{rec.barcode}-{sequence[1]}"

    def check_barcode(self, i):
        for rec in self:
            for product in rec.sub_product_created:
                if f"-{i}" in str(product.barcode):
                    return True


    @api.depends('uom_id')
    def _compute_uom_cat_id(self):
        for rec in self:
            rec.uom_cat_id = rec.uom_id.category_id

    def write(self, vals):
        res = super(ProductTemplateSubUom, self).write(vals)
        for records in self:
            if records.create_other_units:
                if 'other_units_id' in vals:
                    for unit in vals['other_units_id']:
                        if unit[1] in records.other_units_id.ids:
                            if self.env['mrp.bom'].search(
                                    [('product_tmpl_id.name', '=', records.name), ('product_uom_id', '=', unit[1])]):
                                pass
                            else:

                                created_product = self.env['product.template'].create({'name': records.name,
                                                                     'uom_id': unit[1],
                                                                     'uom_po_id': unit[1],
                                                                     'purchase_ok': False,
                                                                     'categ_id': records.categ_id.id
                                                                     })

                                self.env['mrp.bom'].create({'product_tmpl_id': created_product.id,
                                                            'type': 'phantom',
                                                            'product_uom_id': unit[1],
                                                            'bom_line_ids': [
                                                                (0, 0, {
                                                                    'product_id': self.env['product.product'].search(
                                                                        [('name', '=', records.name),
                                                                         ('uom_id', '=', records.uom_id.id)],
                                                                        limit=1).id,
                                                                    'product_uom_id': unit[1]})
                                                            ]
                                                            })
                                if records.barcode:
                                    records.onchange_barcode()
                        elif unit[1] not in records.other_units_id.ids:
                            print(">>>>>>>>>>DDDDDDDD<<<<<<<<<<<<<<")
                            print("unit[1]", unit[1])
                            deleted_bom = self.env['mrp.bom'].search(
                                [('bom_line_ids.product_id.product_tmpl_id', '=', records.id), ('product_uom_id', '=', unit[1]),
                                 ('type', '=', 'phantom')]).unlink()
                            deleted_product = self.env['product.product'].search(
                                [('name', '=', records.name), ('uom_id', '=', unit[1]), ('purchase_ok', '=', False)])
                            deleted_product.unlink()
                elif 'sub_product_created' in vals:
                    print(vals)
                    print("sub_product_created", vals['sub_product_created'])
                    print(vals['sub_product_created'])
                    for deleted_product in vals['sub_product_created']:
                        if deleted_product[1] not in records.sub_product_created.ids:
                            product_to_delete = self.env['product.product'].search([('id', '=', deleted_product[1])])
                            self.env['mrp.bom'].search(
                                [('product_tmpl_id', '=', product_to_delete.product_tmpl_id.id)]).unlink()
                            records.other_units_id -= product_to_delete.uom_id
                            product_to_delete.unlink()
        return res


class ProductProductSubUom(models.Model):
    _inherit = "product.product"

    sub_product_created = fields.Many2one(comodel_name='product.template')

    def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
        """ When the product is a kit, this override computes the fields :
         - 'virtual_available'
         - 'qty_available'
         - 'incoming_qty'
         - 'outgoing_qty'
         - 'free_qty'

        This override is used to get the correct quantities of products
        with 'phantom' as BoM type.
        """
        bom_kits = self.env['mrp.bom']._bom_find(self, bom_type='phantom')
        kits = self.filtered(lambda p: bom_kits.get(p))
        regular_products = self - kits
        res = (
            super(ProductProductSubUom, regular_products)._compute_quantities_dict(lot_id, owner_id, package_id,
                                                                                   from_date=from_date, to_date=to_date)
            if regular_products
            else {}
        )
        qties = self.env.context.get("mrp_compute_quantities", {})
        qties.update(res)
        # pre-compute bom lines and identify missing kit components to prefetch
        bom_sub_lines_per_kit = {}
        prefetch_component_ids = set()
        for product in bom_kits:
            __, bom_sub_lines = bom_kits[product].explode(product, 1)
            bom_sub_lines_per_kit[product] = bom_sub_lines
            for bom_line, __ in bom_sub_lines:
                if bom_line.product_id.id not in qties:
                    prefetch_component_ids.add(bom_line.product_id.id)
        # compute kit quantities
        for product in bom_kits:
            bom_sub_lines = bom_sub_lines_per_kit[product]
            # group lines by component
            bom_sub_lines_grouped = collections.defaultdict(list)
            for info in bom_sub_lines:
                bom_sub_lines_grouped[info[0].product_id].append(info)
            ratios_virtual_available = []
            ratios_qty_available = []
            ratios_incoming_qty = []
            ratios_outgoing_qty = []
            ratios_free_qty = []

            for component, bom_sub_lines in bom_sub_lines_grouped.items():
                component = component.with_context(mrp_compute_quantities=qties).with_prefetch(prefetch_component_ids)
                qty_per_kit = 0
                for bom_line, bom_line_data in bom_sub_lines:
                    if not component.is_storable or float_is_zero(bom_line_data['qty'],
                                                                  precision_rounding=bom_line.product_uom_id.rounding):
                        # As BoMs allow components with 0 qty, a.k.a. optionnal components, we simply skip those
                        # to avoid a division by zero. The same logic is applied to non-storable products as those
                        # products have 0 qty available.
                        continue
                    uom_qty_per_kit = bom_line_data['qty'] / bom_line_data['original_qty']
                    qty_per_kit += bom_line.product_uom_id._compute_quantity(uom_qty_per_kit,
                                                                             bom_line.product_id.uom_id, round=False,
                                                                             raise_if_failure=False)
                if not qty_per_kit:
                    continue
                rounding = component.uom_id.rounding
                component_res = (
                    qties.get(component.id)
                    if component.id in qties
                    else {
                        "virtual_available": float_round(component.virtual_available, precision_rounding=rounding),
                        "qty_available": float_round(component.qty_available, precision_rounding=rounding),
                        "incoming_qty": float_round(component.incoming_qty, precision_rounding=rounding),
                        "outgoing_qty": float_round(component.outgoing_qty, precision_rounding=rounding),
                        "free_qty": float_round(component.free_qty, precision_rounding=rounding),
                    }
                )
                ratios_virtual_available.append(
                    float_round(component_res["virtual_available"] / qty_per_kit, precision_rounding=rounding))
                ratios_qty_available.append(
                    float_round(component_res["qty_available"] / qty_per_kit, precision_rounding=rounding))
                ratios_incoming_qty.append(
                    float_round(component_res["incoming_qty"] / qty_per_kit, precision_rounding=rounding))
                ratios_outgoing_qty.append(
                    float_round(component_res["outgoing_qty"] / qty_per_kit, precision_rounding=rounding))
                ratios_free_qty.append(
                    float_round(component_res["free_qty"] / qty_per_kit, precision_rounding=rounding))
            if bom_sub_lines and ratios_virtual_available:  # Guard against all cnsumable bom: at least one ratio should be present.
                res[product.id] = {
                    'virtual_available': float_round(min(ratios_virtual_available) * bom_kits[product].product_qty,
                                                     precision_rounding=rounding),
                    'qty_available': float_round(min(ratios_qty_available) * bom_kits[product].product_qty,
                                                 precision_rounding=rounding),
                    'incoming_qty': float_round(min(ratios_incoming_qty) * bom_kits[product].product_qty,
                                                precision_rounding=rounding),
                    'outgoing_qty': float_round(min(ratios_outgoing_qty) * bom_kits[product].product_qty,
                                                precision_rounding=rounding),
                    'free_qty': float_round(min(ratios_free_qty) * bom_kits[product].product_qty,
                                            precision_rounding=rounding),
                }
            else:
                res[product.id] = {
                    'virtual_available': 0,
                    'qty_available': 0,
                    'incoming_qty': 0,
                    'outgoing_qty': 0,
                    'free_qty': 0,
                }

        return res
