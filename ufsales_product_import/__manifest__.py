{
    "name": "UF Sales Product Import",
    "version": "19.0.1.1.0",
    "category": "Website",
    "summary": "Import UF Sales catalog, vendors, inventory, and price tiers from JSON + STEP1 CSV exports",
    "license": "LGPL-3",
    "author": "Parameter",
    "website": "https://parameterllc.com",
    "depends": [
        "product",
        "website_sale",
        "stock",
        "purchase",
        "ufs_customer_pricing",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/step1_import_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
