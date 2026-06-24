# Apply the "Duval County" 7.5% sales tax as the Customer Tax on products.
#
# Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/apply_duval_tax.py').read())
#
# Idempotent. Products that already have exactly this tax are skipped.
#
# Notes:
# - taxes_id is the product's "Customer Taxes" (charged on sale orders/invoices).
# - This tax is mapped on the wholesale fiscal position (id 4), so approved
#   resale customers are still auto-exempted; retail/non-exempt customers pay 7.5%.
# - Only ACTIVE products are touched (archived STEP1 stubs are skipped).

# ---- options ----------------------------------------------------------------
TAX_ID = 1                 # "Duval County"
TAX_NAME = "Duval County"
REPLACE = True             # True: make it the ONLY customer tax; False: add alongside existing
SALE_OK_ONLY = False       # True: only sellable products; False: all active products
# -----------------------------------------------------------------------------

Tax = env['account.tax'].sudo()
tax = Tax.browse(TAX_ID).exists()
if not tax or tax.name != TAX_NAME or tax.type_tax_use != 'sale':
    tax = Tax.search([('name', '=', TAX_NAME), ('type_tax_use', '=', 'sale')], limit=1)
if not tax:
    raise Exception("Could not find the Duval County sale tax.")
print("Using tax id=%s  name=%s  amount=%s%%  type=%s" % (
    tax.id, tax.name, tax.amount, tax.type_tax_use))

Template = env['product.template'].sudo()
domain = [('sale_ok', '=', True)] if SALE_OK_ONLY else []
products = Template.search(domain)   # active=True by default
print("scanning %s active product(s)%s" % (
    len(products), " (sale_ok only)" if SALE_OK_ONLY else ""))

if REPLACE:
    to_change = products.filtered(lambda t: t.taxes_id.ids != [tax.id])
    command = [(6, 0, [tax.id])]
else:
    to_change = products.filtered(lambda t: tax.id not in t.taxes_id.ids)
    command = [(4, tax.id)]

print("%s product(s) need updating (%s already correct)" % (
    len(to_change), len(products) - len(to_change)))

done = 0
for i in range(0, len(to_change), 500):
    chunk = to_change[i:i + 500]
    chunk.write({'taxes_id': command})
    done += len(chunk)
    env.cr.commit()
    print("  updated %s/%s" % (done, len(to_change)))

print("done. set Duval County (%s%%) as customer tax on %s product(s)%s." % (
    tax.amount, done, "" if REPLACE else " (added to existing)"))
