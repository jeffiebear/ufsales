# Diagnostics for (1) customer special-price not displaying, and
# (4) one-PO-per-backordered-item. Read-only — changes nothing.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_pricing_and_po.py').read())
#
# Paste the entire output back.

print("\n" + "=" * 70)
print("ITEM 1 — PRICING")
print("=" * 70)

Item = env['product.pricelist.item']
print("\n[A] product.pricelist.item fields present (confirms formula API):")
for f in ('compute_price', 'fixed_price', 'base', 'price_markup',
          'price_discount', 'price_surcharge', 'price_round',
          'applied_on', 'min_quantity'):
    print("    %-16s %s" % (f, f in Item._fields))

print("\n[B] website methods mentioning 'pricelist' (reveals the override hook):")
try:
    W = env['website']
    print("    ", [x for x in dir(W) if 'pricelist' in x.lower()])
except Exception as e:
    print("    website model error:", e)

print("\n[C] product.pricelist fields for website availability:")
PL = env['product.pricelist']
for f in ('website_id', 'selectable', 'code', 'company_id'):
    print("    %-16s %s" % (f, f in PL._fields))

Rule = env['ufs.price.rule'].sudo()
r = Rule.search([('rule_type', '=', 'special'), ('active', '=', True)], limit=1) \
    or Rule.search([('active', '=', True)], limit=1)
if not r:
    print("\n[D] No ufs.price.rule records found — can't sample.")
else:
    r = r[0]
    p, prod = r.partner_id, r.product_id
    pl = p.property_product_pricelist
    print("\n[D] Sample rule:")
    print("    partner :", p.display_name)
    print("    product :", prod.display_name, "| list_price:", prod.list_price,
          "| cost:", prod.standard_price)
    print("    rule    : type=%s special=%s margin=%s markup=%s" % (
        r.rule_type, r.special_price, r.margin_pct, r.markup_pct))
    print("    partner.property_product_pricelist:",
          pl.display_name if pl else None, "(id %s)" % (pl.id if pl else 0))
    print("    partner.ufs_pricelist_id:",
          p.ufs_pricelist_id.display_name if p.ufs_pricelist_id else None)
    it = r.pricelist_item_id
    print("    rule.pricelist_item_id:", it.id if it else None,
          "compute=%s fixed=%s" % (it.compute_price, it.fixed_price) if it else "")
    if pl:
        try:
            price = pl._get_product_price(prod, 1.0)
            print("    >>> pricelist price (qty 1):", price,
                  "  vs list_price:", prod.list_price,
                  "  => %s" % ("OK (special applies)" if abs(price - prod.list_price) > 0.001 else "LEAK (shows list)"))
        except Exception as e:
            print("    _get_product_price error:", e)
        if 'website_id' in PL._fields:
            print("    pricelist.website_id:", pl.website_id.id if pl.website_id else False)
        if 'selectable' in PL._fields:
            print("    pricelist.selectable:", pl.selectable)

print("\n" + "=" * 70)
print("ITEM 4 — PROCUREMENT / PURCHASE ORDERS")
print("=" * 70)

print("\n[E] Buy stock.rules (group propagation drives PO consolidation):")
try:
    for rule in env['stock.rule'].search([('action', '=', 'buy')]):
        print("    '%s'  group_propagation=%s  picking_type=%s" % (
            rule.name, rule.group_propagation_option,
            rule.picking_type_id.name))
except Exception as e:
    print("    stock.rule error:", e)

print("\n[F] Scheduler cron:")
cron = env.ref('stock.ir_cron_scheduler_action', raise_if_not_found=False)
if cron:
    print("    active=%s every %s %s  nextcall=%s" % (
        cron.active, cron.interval_number, cron.interval_type, cron.nextcall))
else:
    print("    stock.ir_cron_scheduler_action not found")

print("\n[G] Routes on a sample purchased product (MTO fragments POs):")
try:
    tmpl = env['product.template'].search(
        [('purchase_ok', '=', True), ('type', 'in', ('consu', 'product'))], limit=1)
    if tmpl:
        print("    '%s' routes: %s" % (tmpl.display_name, tmpl.route_ids.mapped('name')))
    op = env['stock.warehouse.orderpoint'].search_count([])
    print("    reordering rules (orderpoints) in DB:", op)
except Exception as e:
    print("    route check error:", e)

print("\n[H] Recent draft POs grouped by vendor (shows fragmentation):")
try:
    from collections import Counter
    drafts = env['purchase.order'].search([('state', '=', 'draft')])
    by = Counter(po.partner_id.display_name for po in drafts)
    print("    %s draft PO(s) across %s vendor(s):" % (len(drafts), len(by)))
    for vendor, n in by.most_common(10):
        print("       %3d  %s" % (n, vendor))
except Exception as e:
    print("    draft PO scan error:", e)

print("\n=== END ===\n")
