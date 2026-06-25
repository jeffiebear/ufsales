# Inspect why an order's pricelist isn't the customer's per-customer one.
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_order_pricelist.py').read())
# Paste the whole output back.

ORDER_NAME = "S00267"

SO = env['sale.order'].sudo()
o = SO.search([('name', '=', ORDER_NAME)], limit=1)
if not o:
    print("Order %s not found." % ORDER_NAME)
else:
    def plinfo(pl):
        return "%s (id %s)" % (pl.display_name, pl.id) if pl else "None"
    p = o.partner_id
    print("[A] Order:", o.name, "state:", o.state, "create_date:", o.create_date)
    print("    order.pricelist_id        :", plinfo(o.pricelist_id))
    print("[B] order.partner_id (drives pricelist):", p.display_name, "(id %s)" % p.id)
    print("    is this the parent?  parent_id:",
          (p.parent_id.display_name + " (id %s)" % p.parent_id.id) if p.parent_id else "None (is a top-level)")
    print("    commercial_partner_id     :", p.commercial_partner_id.display_name, "(id %s)" % p.commercial_partner_id.id)
    print("    property_product_pricelist:", plinfo(p.property_product_pricelist))
    print("    ufs_pricelist_id          :", plinfo(p.ufs_pricelist_id))

    print("\n[C] The partner we repointed earlier (id 1298):")
    p1298 = env['res.partner'].sudo().browse(1298).exists()
    if p1298:
        print("    name:", p1298.display_name)
        print("    property_product_pricelist:", plinfo(p1298.property_product_pricelist))
        print("    ufs_pricelist_id          :", plinfo(p1298.ufs_pricelist_id))
        print("    >>> order.partner_id == 1298 ?", p.id == 1298)

    print("\n[D] All CELEBRATION-related partners and their pricelists:")
    fam = env['res.partner'].sudo().search([('name', 'ilike', 'CELEBRATION')])
    for f in fam:
        print("    id=%-5s %-45s parent=%-5s prop=%s ufs=%s" % (
            f.id, (f.display_name or '')[:45],
            f.parent_id.id or '-',
            f.property_product_pricelist.id if f.property_product_pricelist else '-',
            f.ufs_pricelist_id.id if f.ufs_pricelist_id else '-'))

print("\n=== END ===\n")
