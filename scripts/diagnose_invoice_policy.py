# Read-only. Confirms WHY an order over-invoices on a partial delivery.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/diagnose_invoice_policy.py').read())
#
# Set ORDER_NAME to a sale order that over-invoiced. Leave '' to skip the
# per-order breakdown and just see the company-wide picture.

ORDER_NAME = ''   # e.g. "S00271"

Template = env['product.template'].with_context(active_test=False).sudo()

# ---- Company-wide picture -------------------------------------------------
phys = [('type', 'in', ('consu', 'product'))]
on_order = Template.search_count(phys + [('invoice_policy', '=', 'order')])
on_deliv = Template.search_count(phys + [('invoice_policy', '=', 'delivery')])
default = env['ir.default'].get('product.template', 'invoice_policy')

print("=== Invoice policy — physical products ===")
print("  on 'Ordered quantities'   (over-invoices): %s" % on_order)
print("  on 'Delivered quantities' (correct)      : %s" % on_deliv)
print("  default for NEW products                 : %s" % (default or '(unset -> Odoo default \"order\")'))
if on_order or (default or 'order') == 'order':
    print("  >>> This is the cause. Run set_invoice_policy_delivery.py to fix.")
else:
    print("  >>> All physical products + default are on delivery. Good.")

# ---- Per-order breakdown --------------------------------------------------
if ORDER_NAME:
    o = env['sale.order'].sudo().search([('name', '=', ORDER_NAME)], limit=1)
    if not o:
        print("\nOrder %s not found." % ORDER_NAME)
    else:
        print("\n=== %s — line-by-line ===" % o.name)
        print("  %-32s %-9s %7s %7s %7s %9s" % (
            'product', 'policy', 'order', 'deliv', 'inv', 'to_inv'))
        for l in o.order_line.filtered(lambda x: not x.display_type):
            print("  %-32s %-9s %7s %7s %7s %9s" % (
                (l.product_id.display_name or '')[:32],
                l.product_id.invoice_policy,
                l.product_uom_qty, l.qty_delivered,
                l.qty_invoiced, l.qty_to_invoice))
        print("  (policy 'order' => 'to_inv' tracks ORDERED, not delivered — "
              "that is the over-invoice.)")

print("\n=== END ===")
