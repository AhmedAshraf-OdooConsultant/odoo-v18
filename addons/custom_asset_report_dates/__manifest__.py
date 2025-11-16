# custom_asset_report_dates/__manifest__.py

# -*- coding: utf-8 -*-
{
    'name': "Custom Asset Report Dates",
    'summary': """
        Modifies the Depreciation Schedule report to use bill dates,
        adds more account columns, and sets PDF to landscape.""",
    'description': """
        - Uses vendor bill dates to calculate opening and added asset values.
        - Adds Fixed Asset, Depreciation, and Expense account columns.
        - Sets the PDF export to landscape to fit the new columns.
        - Adds custom CSS to ensure the table uses the full page width on PDF.
    """,
    'author': "Your Name",
    'website': "https://www.yourcompany.com",
    'category': 'Accounting/Accounting',
    'version': '18.0.1.5.0', # زيادة رقم الإصدار
    'depends': ['account_reports'],
    'data': [], # ملفات الـ XML لم تعد مطلوبة
    # أضف هذا القسم الجديد بالكامل
    'assets': {
        'web.report_assets_common': [
            'custom_asset_report_dates/static/src/css/report_assets.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
