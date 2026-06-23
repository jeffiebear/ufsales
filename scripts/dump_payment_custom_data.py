# Dump payment_custom data/const/template files so we mirror the exact
# Odoo 19 payment.method + payment.provider XML for our new provider.
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/dump_payment_custom_data.py').read())
# Paste the whole output back.

import os

from odoo.addons import payment_custom
base = os.path.dirname(payment_custom.__file__)

rels = [
    'const.py',
    'data/payment_method_data.xml',
    'data/payment_provider_data.xml',
    'views/payment_custom_templates.xml',
    'views/payment_provider_views.xml',
    '__init__.py',
]
for rel in rels:
    p = os.path.join(base, rel)
    print("\n" + "=" * 72)
    print("FILE:", rel)
    print("=" * 72)
    try:
        print(open(p, encoding='utf-8').read())
    except Exception as e:
        print("  (could not read:", repr(e), ")")

# The base payment.method model fields we must populate correctly.
print("\n" + "=" * 72)
print("payment.method model fields")
print("=" * 72)
PM = env['payment.method']
for f in ('name', 'code', 'active', 'is_primary', 'primary_payment_method_id',
          'provider_ids', 'sequence', 'image', 'support_tokenization'):
    print("   %-26s %s" % (f, f in PM._fields))

print("\n=== END ===\n")
