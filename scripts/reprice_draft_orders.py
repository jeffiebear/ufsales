# One-time: realign + reprice existing DRAFT/SENT sale orders so their lines
# reflect the customer's current UFS pricelist (special prices). New orders
# get this automatically; this only fixes orders created before the customer's
# pricelist/rules existed. Confirmed orders are left alone (historical record).
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/reprice_draft_orders.py').read())
#
# Idempotent. Safe to re-run.

SO = env['sale.order'].sudo()
orders = SO.search([('state', 'in', ('draft', 'sent'))])
print("scanning %s draft/sent orders" % len(orders))

realigned = repriced = 0
for o in orders:
    target_pl = o.partner_id.ufs_pricelist_id or o.partner_id.property_product_pricelist
    if not target_pl:
        continue
    if o.pricelist_id != target_pl:
        o.pricelist_id = target_pl.id
        realigned += 1
    # Reprice lines under the (now correct) pricelist. Odoo 19 exposes
    # action_update_prices on sale.order; fall back to _recompute_prices.
    try:
        if hasattr(o, 'action_update_prices'):
            o.action_update_prices()
        elif hasattr(o, '_recompute_prices'):
            o._recompute_prices()
        repriced += 1
    except Exception as e:
        print("  reprice failed for %s: %s" % (o.name, e))
    if (realigned + repriced) % 200 == 0:
        env.cr.commit()

env.cr.commit()
print("done. realigned pricelist on %s orders, repriced %s orders." % (realigned, repriced))
