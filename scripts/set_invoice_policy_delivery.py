# Make invoicing follow DELIVERED quantities, so a partial delivery only
# ever invoices what actually shipped (the rest stays open on the SO and
# invoices when its backorder picking validates later).
#
# Two things have to be true for that, and BOTH are handled here:
#   1) Every existing storable / consumable product is flipped to
#      "Delivered quantities".
#   2) The COMPANY DEFAULT is set to "Delivered quantities" so every NEW
#      or imported product is born that way. Without this, new products
#      default to "Ordered quantities" and silently reintroduce the
#      over-invoicing bug for any order that includes them.
#
# Services stay on "Ordered" — those are deposits, setup fees, etc.
# that should invoice up front, not at delivery.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/set_invoice_policy_delivery.py').read())
#
# Idempotent. Safe to re-run.

# ---- 1) Company default for NEW / imported products -----------------------
# Mirrors Settings -> Sales -> Invoicing -> "Invoicing Policy = Delivered
# quantities" (that UI control just writes this ir.default).
env['ir.default'].set('product.template', 'invoice_policy', 'delivery')
print('default invoice policy for new products -> "delivery"')

# ---- 2) Flip every existing physical product ------------------------------
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
