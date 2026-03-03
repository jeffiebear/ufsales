{
    "name": "UF Sales Catalog Seed",
    "version": "19.0.1.0.1",
    "category": "Website",
    "summary": "Seeds categories, attributes, demo products, and menu links for website_sale",
    "license": "LGPL-3",
    "author": "Parameter",
    "website": "https://parameterllc.com",
    "depends": [
        "website_sale",
        "product",
    ],
    "data": [
        "data/product_public_categories.xml",
        "data/product_attributes.xml",
        "data/website_menu.xml",
    ],
    "demo": [
        "demo/demo_products.xml",
    ],
    "installable": True,
    "application": False,
}
