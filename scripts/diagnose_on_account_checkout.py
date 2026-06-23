# Why doesn't "Pay on Account" show at checkout for a net-terms customer?
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_on_account_checkout.py').read())
# Paste the whole output back.

P = env['payment.provider'].sudo()
prov = P.search([('custom_mode', '=', 'pay_on_account')], limit=1)

print("\n[A] Pay-on-Account provider config:")
if not prov:
    print("    NOT FOUND — module not installed / provider missing.")
else:
    def g(name):
        return prov[name] if name in prov._fields else '(no field)'
    print("    id:", prov.id, "name:", prov.name)
    print("    state:", prov.state)
    print("    is_published (website visible):", g('is_published'))
    print("    journal_id:", prov.journal_id.display_name if 'journal_id' in prov._fields and prov.journal_id else None)
    print("    company_id:", prov.company_id.display_name)
    print("    ufs_requires_payment_terms:", g('ufs_requires_payment_terms'))
    print("    custom_mode:", g('custom_mode'))
    print("    redirect_form_view_id:", prov.redirect_form_view_id.xml_id if 'redirect_form_view_id' in prov._fields and prov.redirect_form_view_id else None)
    print("    payment_method_ids:", [(m.code, 'active=%s' % m.active) for m in prov.payment_method_ids])
    print("    country_ids:", prov.country_ids.mapped('code') or "(all)")
    if 'available_currency_ids' in prov._fields:
        print("    available_currency_ids:", prov.available_currency_ids.mapped('name') or "(all)")
    print("    maximum_amount:", g('maximum_amount'))

print("\n[B] payment.method 'pay_on_account':")
pm = env['payment.method'].sudo().search([('code', '=', 'pay_on_account')], limit=1)
if pm:
    print("    id:", pm.id, "active:", pm.active, "is_primary:", pm.is_primary,
          "providers:", pm.provider_ids.mapped('name'))
else:
    print("    NOT FOUND")

print("\n[C] Simulate the checkout resolver for John Customer's latest order:")
order = env['sale.order'].search([('partner_id.name', 'ilike', 'John Customer')],
                                 order='id desc', limit=1)
if not order:
    order = env['sale.order'].search([], order='id desc', limit=1)
if order:
    term = order.partner_id.property_payment_term_id \
        or order.partner_id.commercial_partner_id.property_payment_term_id
    print("    order=%s partner=%s company=%s amount=%s currency=%s term=%s" % (
        order.name, order.partner_id.display_name, order.company_id.display_name,
        order.amount_total, order.currency_id.name, term.name if term else "(none)"))
    try:
        comp = P._get_compatible_providers(
            order.company_id.id, order.partner_id.id, order.amount_total,
            currency_id=order.currency_id.id, sale_order_id=order.id,
        )
        print("    compatible providers:", [(c.id, c.name) for c in comp])
        print("    >>> Pay on Account included?", bool(prov and prov in comp))
    except Exception as e:
        print("    resolver error (with sale_order_id):", repr(e))
        try:
            comp = P._get_compatible_providers(
                order.company_id.id, order.partner_id.id, order.amount_total)
            print("    compatible (no so):", [(c.id, c.name) for c in comp])
            print("    >>> Pay on Account included?", bool(prov and prov in comp))
        except Exception as e2:
            print("    resolver error:", repr(e2))
else:
    print("    no order found to test")

print("\n=== END ===\n")
