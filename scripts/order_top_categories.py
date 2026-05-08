# Set the display order of the top-level catalog categories.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/order_top_categories.py').read())
#
# Idempotent. Sets `sequence` on the 5 top-level public categories so the
# catalog bar / megamenu shows them in this order:
#
#   1. Janitorial Supplies
#   2. Food Service
#   3. Soaps and Sanitizers
#   4. Gloves and Safety
#   5. Packaging
#
# Sort key for the menu builder is `sequence, name, id`, so giving each
# wrapper a small distinct sequence wins over alphabetical.

ORDER = [
    "Janitorial Supplies",
    "Food Service",
    "Soaps and Sanitizers",
    "Gloves and Safety",
    "Packaging",
]

Cat = env['product.public.category'].with_context(active_test=False).sudo()

for idx, name in enumerate(ORDER, start=1):
    cat = Cat.search([('name', '=', name), ('parent_id', '=', False)], limit=1)
    if not cat:
        print('  SKIP "%s" — not found at root' % name)
        continue
    if cat.sequence != idx:
        cat.sequence = idx
        print('  set "%s" id=%s sequence=%s' % (name, cat.id, idx))
    else:
        print('  ok   "%s" id=%s sequence=%s (already)' % (name, cat.id, idx))

env.cr.commit()
print('done.')
