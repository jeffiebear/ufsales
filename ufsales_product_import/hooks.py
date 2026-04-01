from odoo import SUPERUSER_ID, api

# hooks.py file

def post_init_hook(*args):
    if len(args) == 1:
        env = args[0]
    elif len(args) == 2:
        cr, _registry = args
        env = api.Environment(cr, SUPERUSER_ID, {})
    else:
        raise TypeError("post_init_hook expected env or (cr, registry)")

    env["ufsales.product.importer"].run_import()
