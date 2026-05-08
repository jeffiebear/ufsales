{
    "name": "UF Sales Website Styles",
    "version": "19.0.1.0.5",
    "category": "Website",
    "summary": "UF Sales branding assets for website + ecommerce",
    "license": "LGPL-3",
    "author": "Parameter",
    "website": "https://parameterllc.com",
    "depends": [
        "website",
        "website_sale",
        "ufsales_product_import",
    ],
    "data": [
        "views/website_layout.xml",
        "views/website_sale_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "uf_sales_website/static/src/css/uf_sales.css",
        ],
    },
    "installable": True,
    "application": False,
}
