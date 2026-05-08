# Prune pre-existing demo product.public.category records that came with the
# website install but were never wired up to any UF Sales product.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/prune_demo_categories.py').read())
#
# Safe to re-run. Touches ONLY product.public.category records where:
#   - ufsales_source_path IS NULL  (i.e. not from STEP1 import)
#   - product_tmpl_ids is empty (no products attached, directly or via descendants)
#
# Internal product.category records are NOT touched — those 4 root entries
# (Goods/Expenses/Services/Deliveries) are core Odoo and must stay.

Cat = env['product.public.category'].with_context(active_test=False).sudo()

# Find every public category that is "demo" (no source_path).
demo = Cat.search([('ufsales_source_path', '=', False)])
print('candidates (no source_path): %s' % len(demo))

# Walk descendants; only delete a category if every category in its subtree
# has zero products attached. This protects against accidentally killing a
# real category that happens to be missing the source_path stamp.
def _subtree(cat):
    out = cat
    if cat.child_id:
        for c in cat.child_id:
            out |= _subtree(c)
    return out

to_keep_for_products = Cat.browse()
for c in demo:
    sub = _subtree(c)
    total_products = sum(len(x.product_tmpl_ids) for x in sub)
    if total_products:
        to_keep_for_products |= c
        print('  KEEP %s "%s" — subtree has %s products' % (c.id, c.name, total_products))

doomed = demo - to_keep_for_products

# Include their demo descendants too (also stamped with no source_path).
all_doomed = Cat.browse()
for c in doomed:
    all_doomed |= _subtree(c)
# Don't accidentally include real (source_path-stamped) descendants.
all_doomed = all_doomed.filtered(lambda x: not x.ufsales_source_path)

print('will delete %s public categories' % len(all_doomed))
for c in all_doomed.sorted('id'):
    parent = c.parent_id.name if c.parent_id else '(root)'
    print('  - %s "%s" (parent=%s)' % (c.id, c.name, parent))

all_doomed.unlink()
env.cr.commit()
print('done.')
