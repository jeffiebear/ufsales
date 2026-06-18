# Flip every storable / consumable product to "Delivered quantities"
# invoicing so auto-invoice-on-delivery picks up the right qty_to_invoice.
#
# Services stay on "Ordered" — those are deposits, setup fees, etc.
# that should invoice up front, not at delivery.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/set_invoice_policy_delivery.py').read())
#
# Idempotent. Safe to re-run.

Template = env['product.template'].with_context(active_test=False).sudo()

# Storable + consumable. Services skipped.
PHYSICAL_TYPES = ('consu', 'product')

candidates = Template.search([
    ('type', 'in', PHYSICAL_TYPES),
    ('invoice_policy', '!=', 'delivery'),
])
print('found %s product(s) not yet on delivery invoicing' % len(candidates))

batch = 500
done = 0
for i in range(0, len(candidates), batch):
    chunk = candidates[i:i + batch]
    chunk.write({'invoice_policy': 'delivery'})
    done += len(chunk)
    print('  switched %s/%s' % (done, len(candidates)))
    env.cr.commit()

# Confirm what's left.
remaining_order = Template.search_count([
    ('type', 'in', PHYSICAL_TYPES),
    ('invoice_policy', '=', 'order'),
])
remaining_services = Template.search_count([
    ('type', '=', 'service'),
    ('invoice_policy', '=', 'order'),
])
print('done. physical products still on order-policy: %s' % remaining_order)
print('services left on order-policy (intentional): %s' % remaining_services)
