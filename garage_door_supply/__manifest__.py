{
    'name': 'AA Impact Garage Door Supply',
    'version': '19.0.1.0.0',
    'summary': 'Complete garage door supply store configuration',
    'description': """
        Custom module for AA Impact Garage Door Supply.
        - Product categories for garage door parts
        - B2B eCommerce configuration
        - Warehouse & inventory routes
        - Point of Sale setup
        - Manufacturer dispatch workflow
    """,
    'author': 'AA Impact Garage Door Supply',
    'category': 'Sales',
    'depends': [
        'sale_management',
        'purchase',
        'stock',
        'account',
        'website_sale',
        'point_of_sale',
        'mrp',
        'stock_dropshipping',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_category_data.xml',
        'data/warehouse_data.xml',
        'data/pos_config_data.xml',
        'data/website_data.xml',
        'data/partners_taxes_data.xml',
        'data/arrow_products_data.xml',
        'data/hinge_additions_data.xml',
        'views/website_brand.xml',
        'views/website_homepage.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
