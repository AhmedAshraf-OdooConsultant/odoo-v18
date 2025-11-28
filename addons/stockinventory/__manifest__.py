{
    'name': 'Stock Aging Inventory', 
    'version': '18.0.1.0.0', 
    'summary': """Stock Aging Report""",
    'description': """Stock Aging Report""",
    'author': "Swati Khandelwal" ,
    'category': 'Excel Sheet',
    'depends': ['point_of_sale', 'stock'],
    'data': [
       'security/ir.model.access.csv', 
       'wizard/stock_wizard.xml',
    ],
    'images' : ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'application': True,
}

