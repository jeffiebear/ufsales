# Why does a customer's blanket pricelist win over their product overrides?
# Checks whether the pricelist the SALE ORDER uses is the same one that holds
# the customer's special-price overrides.
#
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_partner_pricing.py').read())
# Paste the whole output back.

PARTNER_NAME = "John Customer"   # <-- set to the customer you're testing
PRODUCT_CODE = ""                 # optional: a product code they should have an override for

Partner = env['res.partner'].sudo()
Item = env['product.pricelist.item'].sudo()
Rule = env['ufs.price.rule'].sudo()

partner = Partner.search([('name', 'ilike', PARTNER_NAME)], limit=1)
if not partner:
    print("No partner matching %r" % PARTNER_NAME)
else:
    order_pl = partner.property_product_pricelist
    ufs_pl = partner.ufs_pricelist_id
    print("[A] Partner:", partner.display_name, "(id %s)" % partner.id)
    print("    property_product_pricelist (ORDER uses this):",
          order_pl.display_name if order_pl else None, "(id %s)" % (order_pl.id if order_pl else 0))
    print("    ufs_pricelist_id (overrides SHOULD live here):",
          ufs_pl.display_name if ufs_pl else None, "(id %s)" % (ufs_pl.id if ufs_pl else 0))
    same = order_pl and ufs_pl and order_pl.id == ufs_pl.id
    print("    >>> SAME pricelist?", bool(same),
          "" if same else "  <-- MISMATCH: order won't see the override pricelist's items")

    print("\n[B] Customer's price rules (overrides) and where their item lives:")
    rules = Rule.search([('partner_id', '=', partner.id)])
    print("    %s rule(s)" % len(rules))
    for r in rules[:25]:
        it = r.pricelist_item_id
        print("    rule id=%s type=%-8s product=%-30s item_id=%s item_pl=%s" % (
            r.id, r.rule_type,
            (r.product_id.display_name or '')[:30],
            it.id or False,
            it.pricelist_id.display_name if it and it.pricelist_id else None))

    # pick a product to test: explicit code, else first rule's product
    product = None
    if PRODUCT_CODE:
        product = env['product.product'].sudo().search([('default_code', '=', PRODUCT_CODE)], limit=1)
    if not product and rules:
        product = rules[0].product_id

    if product and order_pl:
        print("\n[C] Resolution for product:", product.display_name)
        print("    list_price:", product.list_price, " cost:", product.standard_price)
        for plname, pl in [("ORDER pl", order_pl), ("UFS pl", ufs_pl)]:
            if not pl:
                continue
            items = Item.search(['|',
                                 ('product_id', '=', product.id),
                                 ('product_tmpl_id', '=', product.product_tmpl_id.id),
                                 ('pricelist_id', '=', pl.id)])
            globs = Item.search([('pricelist_id', '=', pl.id), ('applied_on', '=', '3_global')])
            print("    --- %s: %s (id %s) ---" % (plname, pl.display_name, pl.id))
            for i in (items | globs):
                print("        item id=%s applied_on=%s min_qty=%s compute=%s fixed=%s pct=%s markup=%s" % (
                    i.id, i.applied_on, i.min_quantity, i.compute_price,
                    getattr(i, 'fixed_price', None),
                    getattr(i, 'price_discount', None),
                    getattr(i, 'price_markup', None) if 'price_markup' in i._fields else 'n/a'))
            try:
                print("        _get_product_price(qty 1):", pl._get_product_price(product, 1.0))
            except Exception as e:
                print("        price error:", e)

print("\n=== END ===\n")
