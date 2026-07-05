# -*- coding: utf-8 -*-
{
    'name': 'AKSHAB - Retail Sales Report | تقرير مبيعات التجزئة',
    'version': '18.0.1.10.0',
    'category': 'Point of Sale',
    'summary': 'تقرير مبيعات التجزئة - شركة أخشاب البخور للتجارة',
    'description': """
تقرير مبيعات نقاط البيع التفصيلي - أخشاب البخور
================================================
تقرير PDF احترافي بالهوية البصرية للشركة يشمل:
  1. إجمالي المبيعات لكل نقطة بيع (مع عدد الفواتير والعملاء الجدد/القدامى)
  2. فواتير المبيعات مرتبة تنازلياً
  3. فواتير مرتجعات المبيعات مرتبة تنازلياً
  4. مبيعات المنتجات مقسمة حسب فئة المنتج
  5. مبيعات الموظفين مقسمة حسب نقطة البيع
  6. تحليل الخصومات (برامج الخصم + الخصومات العامة اليدوية)
""",
    'author': 'Tas-heel Solutions - Ahmed Ashraf',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'pos_loyalty',
        'pos_discount',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/report_paperformat.xml',
        'report/pos_sales_report_action.xml',
        'report/pos_sales_report_templates.xml',
        'wizard/pos_sales_report_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
