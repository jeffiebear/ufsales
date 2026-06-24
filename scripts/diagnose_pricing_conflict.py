# Why does a customer's blanket/bracket rule win over their product-specific
# special price on a sale order? Dumps the competing pricelist items and shows
# what Odoo's resolver actually returns, and why.
#
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_pricing_conflict.py').read())
# Paste the whole output back.
#
# Optional: hard-code a specific case by setting these, else it auto-finds one.
PARTNER_NAME = ""   # e.g. "720 GLASSWORKS"
PRODUCT_CODE = ""   # e.g. "BB-36X850-RL"

Item = env['product.pricelist.item'].sudo()
Rule = env['ufs.price.rule'].sudo()
Pricelist = env['product.pricelist'].sudo()

print("\n[A] product.pricelist.item _order (resolution order):")
print("   ", Item._order)

# ---- locate a conflict: a customer pricelist holding BOTH a special item
#      and a bracket-mirror item for the same product ----
target = None  # (pricelist, product, special_item, bracket_item)

if PARTNER_NAME and PRODUCT_CODE:
    partner = env['res.partner'].sudo().search([('name', '=', PARTNER_NAME)], limit=1)
    product = env['product.product'].sudo().search([('default_code', '=', PRODUCT_CODE)], limit=1)
    pl = partner.ufs_pricelist_id if partner else False
    if pl and product:
        items = Item.search([('pricelist_id', '=', pl.id),
                             ('product_id', '=', product.id)])
        sp = items.filtered(lambda i: not i.ufs_bracket_source_id)[:1]
        br = items.filtered(lambda i: i.ufs_bracket_source_id)[:1]
        target = (pl, product, sp, br)
else:
    mirrors = Item.search([('ufs_bracket_source_id', '!=', False),
                           ('product_id', '!=', False)], limit=400)
    for m in mirrors:
        sp = Item.search([('pricelist_id', '=', m.pricelist_id.id),
                          ('product_id', '=', m.product_id.id),
                          ('ufs_bracket_source_id', '=', False)], limit=1)
        if sp:
            target = (m.pricelist_id, m.product_id, sp, m)
            break

if not target or not target[1]:
    print("\nNo customer pricelist found with BOTH a bracket mirror and a "
          "special item for the same product.")
    print("Bracket mirrors total:", Item.search_count([('ufs_bracket_source_id', '!=', False)]))
    print("Set PARTNER_NAME + PRODUCT_CODE at the top to inspect a specific case.")
else:
    pl, product, sp, br = target
    print("\n[B] Conflict case:")
    print("    pricelist:", pl.display_name, "(id %s)" % pl.id)
    print("    product  :", product.display_name)
    print("    list_price:", product.list_price, " cost:", product.standard_price)

    def dump(i, tag):
        if not i:
            print("    %-8s (none)" % tag)
            return
        print("    %-8s id=%s applied_on=%s min_qty=%s compute=%s fixed=%s "
              "pct=%s markup=%s seq=%s bracket_src=%s date=%s..%s" % (
                  tag, i.id, i.applied_on, i.min_quantity, i.compute_price,
                  getattr(i, 'fixed_price', None),
                  getattr(i, 'price_discount', None),
                  getattr(i, 'price_markup', None) if 'price_markup' in i._fields else 'n/a',
                  i.sequence if 'sequence' in i._fields else 'n/a',
                  i.ufs_bracket_source_id.id or False,
                  i.date_start or '-', i.date_end or '-'))

    print("\n[C] All items on this pricelist for this product (in _order):")
    allitems = Item.search([('pricelist_id', '=', pl.id),
                            ('product_id', '=', product.id)])
    # also pull template-level + global items that could match
    tmpl_items = Item.search([('pricelist_id', '=', pl.id),
                              ('product_tmpl_id', '=', product.product_tmpl_id.id)])
    glob = Item.search([('pricelist_id', '=', pl.id),
                        ('applied_on', '=', '3_global')])
    seen = set()
    for i in (allitems | tmpl_items | glob):
        if i.id in seen:
            continue
        seen.add(i.id)
        tag = 'BRACKET' if i.ufs_bracket_source_id else (
            'SPECIAL' if i == sp else 'other')
        dump(i, tag)

    print("\n[D] What the resolver returns:")
    for qty in (1.0, 5.0, 100.0):
        try:
            res = pl._compute_price_rule(product, qty)
            entry = res.get(product.id)
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                price, rule_id = entry[0], entry[1]
                rid_item = Item.browse(rule_id) if rule_id else None
                kind = ('BRACKET' if rid_item and rid_item.ufs_bracket_source_id
                        else 'SPECIAL' if rid_item == sp else 'other/none')
                print("    qty %-6s -> price %s  (matched item id=%s, %s)" % (
                    qty, price, rule_id, kind))
            else:
                print("    qty %-6s -> %s" % (qty, entry))
        except Exception as e:
            try:
                p = pl._get_product_price(product, qty)
                print("    qty %-6s -> price %s (rule id unavailable: %s)" % (qty, p, e))
            except Exception as e2:
                print("    qty %-6s -> error %s" % (qty, e2))

    print("\n[E] The customer's special RULE (source of truth):")
    partner = env['res.partner'].sudo().search([('ufs_pricelist_id', '=', pl.id)], limit=1)
    if partner:
        rr = Rule.search([('partner_id', '=', partner.id),
                          ('product_id', '=', product.id)], limit=1)
        if rr:
            print("    rule id=%s type=%s special=%s margin=%s markup=%s -> evaluated %s" % (
                rr.id, rr.rule_type, rr.special_price, rr.margin_pct,
                rr.markup_pct, rr._evaluate_price()))
        else:
            print("    (no ufs.price.rule for this partner+product)")

print("\n=== END ===\n")
