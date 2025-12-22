# -*- coding: utf-8 -*-
{
    'name': 'UOM in Product',

        'depends': ['product','uom','mrp'],
    'data': [

        'views/product_template_uom_inherit_view.xml',
        'views/import_product_server.xml',
        'views/ref_uom_auto_action.xml',
		'views/res_config_setting.xml',
],
    'images': [
    ],
    'installable': True,
    'application': True,
    'license': "AGPL-3",
}
