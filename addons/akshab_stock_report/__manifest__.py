# -*- coding: utf-8 -*-
{
    'name': 'Akshab – Inventory Reports (تقارير المخزون)',
    'summary': 'Executive inventory reports and performance dashboard: comprehensive status, aging, turnover, '
               'stagnant / slow / active items — PDF & Excel, Akshab visual identity.',
    'description': """
Akshab Inventory Status Report
==============================
Management-ready inventory report (Arabic RTL, Akshab dark-green / gold identity):

* Wizard: as-of date, warehouses (branches), categories, products, aging buckets,
  stagnation / slow-moving thresholds, sales-analysis window, liquidation discount.
* Inventory aging (FIFO from receipt moves) by bucket, category and warehouse.
  Negative branch balances are never aged or valued, and a receipt arriving after a
  negative balance covers it first (only the remainder is aged).
* Classification of every product: active / slow-moving / stagnant / new / out-of-stock.
* Automatic recommendations (transfer, discount, liquidation, stop buying, reorder)
  with expected cash from liquidating stagnant stock.
* Output as PDF (QWeb, landscape) or Excel (multi-sheet, RTL, branded).
* Interactive inventory performance dashboard (OWL client action) combining the aging,
  turnover and item-status analyses with every wizard filter, previous-period comparison,
  branch / category comparisons, ranked lists and trend charts.
""",
    'version': '18.0.5.1.0',
    'category': 'Inventory/Inventory',
    'author': 'Tasheel Solutions – Ahmed',
    'website': 'https://www.akshab.sa',
    'license': 'LGPL-3',
    'depends': ['stock', 'stock_account'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'report/stock_report_reports.xml',
        'report/stock_report_templates.xml',
        'report/stock_reports_templates.xml',
        'wizard/stock_report_wizard_views.xml',
        'wizard/stock_reports_views.xml',
        'views/dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'akshab_stock_report/static/src/dashboard/dashboard.scss',
            'akshab_stock_report/static/src/dashboard/dashboard.xml',
            'akshab_stock_report/static/src/dashboard/dashboard.js',
        ],
    },
    'installable': True,
}
