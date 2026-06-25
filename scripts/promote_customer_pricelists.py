# Backfill: point every customer's ORDER pricelist at their own UFS pricelist
# (with a global fallback that defers to their current margin tier), so their
# product-specific overrides actually apply on sale orders. Then reprice open
# draft/sent orders.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/promote_customer_pricelists.py').read())
#
# Idempotent. Safe to re-run. Confirmed orders are left untouched.

Partner = env['res.partner'].with_context(active_test=False).sudo()

partners = Partner.search([('ufs_pricelist_id', '!=', False)])
print("customers with a UFS pricelist: %s" % len(partners))

promoted = 0
for p in partners:
    before = p.property_product_pricelist
    p._ufs_promote_pricelist()
    after = p.property_product_pricelist
    if before != after:
        promoted += 1
        print("  %-45s  %s -> %s" % (
            (p.display_name or '')[:45],
            before.display_name if before else None,
            after.display_name if after else None))
    if promoted and promoted % 200 == 0:
        env.cr.commit()
env.cr.commit()
print("repointed %s customer(s) to their own pricelist." % promoted)

# ---- reprice open draft/sent orders so existing quotes pick up overrides ----
SO = env['sale.order'].sudo()
orders = SO.search([('state', 'in', ('draft', 'sent'))])
print("\nrepricing %s draft/sent order(s)" % len(orders))
realigned = repriced = 0
for o in orders:
    target = o.partner_id.property_product_pricelist
    if target and o.pricelist_id != target:
        o.pricelist_id = target.id
        realigned += 1
    try:
        if hasattr(o, 'action_update_prices'):
            o.action_update_prices()
        elif hasattr(o, '_recompute_prices'):
            o._recompute_prices()
        repriced += 1
    except Exception as e:
        print("  reprice failed for %s: %s" % (o.name, e))
    if repriced and repriced % 200 == 0:
        env.cr.commit()
env.cr.commit()
print("done. realigned %s order pricelists, repriced %s order(s)." % (realigned, repriced))
