from odoo import models, fields, api, _

class ProductTemplateUom(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        res = super(ProductTemplateUom, self).write(vals)
        for records in self:
            if records.create_other_units:
                if 'other_units_id' in vals:
                    for unit in vals['other_units_id']:
                        if unit[1] in records.other_units_id.ids:
                            if self.env['mrp.bom'].search(
                                    [('product_tmpl_id.name', '=', records.name), ('product_uom_id', '=', unit[1])]):
                                pass
                            else:
                                print("created created")
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
                                                                        [('product_tmpl_id', '=', records.id),
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