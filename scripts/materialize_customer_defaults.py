# Make each customer's Default Pricing Scheme (ufs_default_price_opt) actually
# drive their prices, by materialising it as a GLOBAL rule on their per-customer
# pricelist. Then point their order pricelist at it and reprice open quotes.
#
#   * 'P50' / 'M40' (with a number) -> global margin/markup rule
#   * 'I'                           -> no global rule (catalog list price)
#   * bare 'P' / 'M' (no number)    -> SKIPPED + reported (ambiguous: a bare
#                                      'P' would mean 0% margin = cost). Give
#                                      these customers a number to apply a margin.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/materialize_customer_defaults.py').read())
#
# Idempotent. Safe to re-run. Confirmed orders are never touched.

from collections import Counter

Partner = env['res.partner'].with_context(active_test=False).sudo()
partners = Partner.search([('ufs_pricelist_id', '!=', False)])
print("per-customer pricelists: %s" % len(partners))

set_count = remove_count = skip_count = 0
skipped = []   # (name, opt) needing a real percentage
plan_dist = Counter()

for i, p in enumerate(partners, 1):
    action, _vals = p._ufs_default_item_plan(p.ufs_pricelist_id)
    plan_dist[(action, (p.ufs_default_price_opt or '').strip().upper())] += 1
    p._ufs_sync_default_pricelist_item()
    if action == 'set':
        set_count += 1
    elif action == 'remove':
        remove_count += 1
    else:
        skip_count += 1
        if (p.ufs_default_price_opt or '').strip():
            skipped.append((p.display_name, p.ufs_default_price_opt))
    # Point the order pricelist at the per-customer one.
    p._ufs_promote_pricelist()
    if i % 200 == 0:
        env.cr.commit()
        print("  processed %s/%s" % (i, len(partners)))
env.cr.commit()

print("\n--- default rules ---")
print("  materialised (margin/markup): %s" % set_count)
print("  list price (no rule)        : %s" % remove_count)
print("  skipped (ambiguous/unset)   : %s" % skip_count)

if skipped:
    print("\n--- SKIPPED: need an explicit percentage (still at list price) ---")
    for name, opt in skipped[:60]:
        print("  %-50s opt=%r" % ((name or '')[:50], opt))
    if len(skipped) > 60:
        print("  ... and %s more" % (len(skipped) - 60))

# ---- reprice open draft/sent orders so quotes pick up the new prices ----
SO = env['sale.order'].sudo()
orders = SO.search([('state', 'in', ('draft', 'sent'))])
print("\nrepricing %s open order(s)" % len(orders))
realigned = repriced = 0
for i, o in enumerate(orders, 1):
    target = o.partner_id.property_product_pricelist
    try:
        if target and o.pricelist_id.id != target.id:
            o.pricelist_id = target.id
            realigned += 1
        if hasattr(o, 'action_update_prices'):
            o.action_update_prices()
        elif hasattr(o, '_recompute_prices'):
            o._recompute_prices()
        repriced += 1
    except Exception as e:
        print("  reprice failed for %s: %s" % (o.name, e))
    if i % 200 == 0:
        env.cr.commit()
env.cr.commit()
print("done. realigned %s pricelists, repriced %s order(s)." % (realigned, repriced))
