{
    "name": "UFS Wholesale Access",
    "version": "19.0.1.2.1",
    "category": "Website",
    "summary": "Wholesale signup, approval workflow, and eCommerce access control",
    "license": "LGPL-3",
    "author": "Parameter",
    "website": "https://parameterllc.com",
    "depends": [
        "website_sale",
        "auth_signup",
        "mail",
        "sale_management",
        "account",
    ],
    "data": [
        "data/mail_templates.xml",
        "data/ir_config_parameter_data.xml",
        "views/auth_signup_templates.xml",
        "views/website_sale_templates.xml",
        "views/res_users_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}

