{
    "name": "Inventory Age Report",
    "author": "Fsolutions",
    "depends": ["stock", "purchase", "sale_management"],
    "data": [
        "security/ir.model.access.csv",
        "report/age_breakdown_report_views.xml",
        "wizard/inventory_age_breakdown_report_views.xml",
    ],

    "auto_install": False,
    "application": False,
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "assets": {
        "web.assets_backend": ["inventory_age_report/static/src/js/action_manager.js"]
    },
    "installable": True,
}
