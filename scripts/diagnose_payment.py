# Diagnostics for the website checkout payment customization
# (CC for all; "on account / net terms" only for customers with terms).
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_payment.py').read())
# Paste the whole output back.

import inspect

PP = env['payment.provider'].sudo()

print("\n[A] _get_compatible_providers (the checkout filter hook):")
m = getattr(PP, '_get_compatible_providers', None)
print("    exists:", bool(m))
if m:
    try:
        print("    signature:", str(inspect.signature(m)))
    except Exception as e:
        print("    signature error:", e)

print("\n[B] payment providers configured:")
for p in PP.search([]):
    print("    id=%-3s state=%-9s code=%-12s name=%r published=%s" % (
        p.id, p.state, p.code, p.name, getattr(p, 'is_published', 'n/a')))

print("\n[C] payment.provider relevant fields present:")
for f in ('code', 'custom_mode', 'state', 'is_published', 'sequence'):
    print("    %-14s %s" % (f, f in PP._fields))

print("\n[D] partner payment-term field:")
RP = env['res.partner']
print("    property_payment_term_id present:", 'property_payment_term_id' in RP._fields)

# How many customers actually have payment terms (sizes the impact)
try:
    with_terms = RP.search_count([('property_payment_term_id', '!=', False), ('customer_rank', '>', 0)])
    print("    customers WITH payment terms:", with_terms)
except Exception as e:
    print("    count error:", e)

print("\n[E] checkout method that lists providers (verify override point):")
try:
    WS = env['website']
    print("    website methods w/ 'provider'/'payment':",
          [x for x in dir(WS) if 'provider' in x.lower() or 'payment' in x.lower()][:20])
except Exception as e:
    print("    error:", e)

print("\n=== END ===\n")
