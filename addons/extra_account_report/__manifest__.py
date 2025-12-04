# -*- coding: utf-8 -*-
{
    'name': 'Extra Filter Account Report',
    'version': '1.0',
    'category': 'Accounting',
    'summary': '',
    'description': """""",
    'depends': ['account_reports', 'account'],
    'data': [
        'data/partner_ledger.xml',
        'views/account_report_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'extra_account_report/static/src/js/filter_extra_options.xml',
            'extra_account_report/static/src/js/filters.xml',
            'extra_account_report/static/src/js/filters.js',
            'extra_account_report/static/src/js/filters_1.js',
            'extra_account_report/static/src/js/controller.js',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
