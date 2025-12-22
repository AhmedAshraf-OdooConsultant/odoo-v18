# -*- coding: utf-8 -*-
{
    "name": "Stock Card Report",
        "license": "LGPL-3",
    "author": "Jason Vu",
    "category": "Warehouse",
    "version": "1.0",
    "depends": ["stock_account", 'uom_in_product'],
    "data": [
        "data/stock_move_line_data.xml",
        "security/ir.model.access.csv",
        "wizard/imex_inventory_report_wizard_view.xml",
        "reports/template.xml",
        "reports/imex_inventory_report_views.xml",
        "reports/imex_inventory_details_report_views.xml",
    ],
    "images": [
],
    "installable": True,
}
