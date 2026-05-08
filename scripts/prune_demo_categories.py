# Prune pre-existing demo product.public.category records that came with the
# website install but were never wired up to any UF Sales product.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/prune_demo_categories.py').read())
#
# Idempotent. Safe to re-run.
#
# Strategy: leaf-by-leaf. In each pass, find every demo record (no
# ufsales_source_path) that has no children and no products, delete them,
# and repeat. This naturally peels demo subtrees from the bottom up — any
# parent that still has products through a non-demo descendant is left alone
# (because that descendant will keep the parent's child_id non-empty).
#
# Internal product.category records are NOT touched — those root entries
# (Goods/Expenses/Services/Deliveries) are core Odoo and must stay.

Cat = env['product.public.category'].with_context(active_test=False).sudo()

total_deleted = 0
pass_no = 0
while True:
    pass_no += 1
    # demo leaves: no source_path, no children, no products
    demo_leaves = Cat.search([
        ('ufsales_source_path', '=', False),
    ]).filtered(lambda c: not c.child_id and not c.product_tmpl_ids)
    if not demo_leaves:
        break
    print('pass %s: deleting %s demo leaves' % (pass_no, len(demo_leaves)))
    for c in demo_leaves.sorted('id'):
        parent = c.parent_id.name if c.parent_id else '(root)'
        print('  - %s "%s" (parent=%s)' % (c.id, c.name, parent))
    total_deleted += len(demo_leaves)
    demo_leaves.unlink()

remaining = Cat.search_count([('ufsales_source_path', '=', False)])
print('total deleted: %s' % total_deleted)
print('remaining demo records (have products via descendants): %s' % remaining)

env.cr.commit()
print('done.')
