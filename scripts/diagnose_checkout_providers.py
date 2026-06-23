# Why do/don't payment providers appear at website checkout?
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_checkout_providers.py').read())
# Paste the whole output back.

P = env['payment.provider'].sudo()

print("\n[A] Is the UFS terms-gate field deployed?")
have = 'ufs_requires_payment_terms' in P._fields
print("    ufs_requires_payment_terms field present:", have)
if have:
    flagged = P.search([('ufs_requires_payment_terms', '=', True)])
    print("    providers flagged 'Requires Payment Terms':",
          [(p.id, p.name) for p in flagged])

print("\n[B] Enabled/test providers, publish state, and their payment methods:")
for p in P.search([('state', 'in', ('enabled', 'test'))]):
    print("    id=%-3s %-28r state=%-8s published=%s custom_mode=%s" % (
        p.id, p.name, p.state, p.is_published, getattr(p, 'custom_mode', None)))
    pms = p.payment_method_ids if 'payment_method_ids' in p._fields else P.browse()
    if not pms:
        print("        (no payment methods linked)")
    for m in pms:
        print("        method: %-22r active=%s published=%s" % (
            m.name, m.active, getattr(m, 'is_published', 'n/a')))

print("\n[C] Simulate checkout provider resolution for a recent order:")
order = env['sale.order'].search([('state', 'in', ('draft', 'sent'))],
                                 order='id desc', limit=1)
if not order:
    print("    no draft/sent order to test with")
else:
    p_term = order.partner_id.property_payment_term_id \
        or order.partner_id.commercial_partner_id.property_payment_term_id
    print("    order=%s partner=%s  payment_term=%s" % (
        order.name, order.partner_id.display_name,
        p_term.name if p_term else "(none)"))
    try:
        comp = P._get_compatible_providers(sale_order_id=order.id)
        print("    compatible providers returned:", [(c.id, c.name) for c in comp])
    except Exception as e:
        print("    _get_compatible_providers(sale_order_id=...) error:", repr(e))
        # try a couple of alternative call conventions
        for kw in ({'order_id': order.id}, {}):
            try:
                comp = P._get_compatible_providers(**kw)
                print("    fallback call %s ->" % kw, [(c.id, c.name) for c in comp])
                break
            except Exception as e2:
                print("    fallback %s error:" % kw, repr(e2))

print("\n=== END ===\n")
