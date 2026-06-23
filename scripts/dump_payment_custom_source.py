# Dump the installed payment_custom module source so we can build a
# correct "Pay on Account" provider against the real Odoo 19 API.
# Read-only. Run from odoo-bin shell:
#   exec(open('/home/odoo/src/user/scripts/dump_payment_custom_source.py').read())
# Paste the WHOLE output back (it's a small module).

import os

try:
    from odoo.addons import payment_custom
    base = os.path.dirname(payment_custom.__file__)
except Exception as e:
    print("could not locate payment_custom:", repr(e))
    base = None

if base:
    print("payment_custom path:", base)
    rels = [
        'models/payment_provider.py',
        'models/payment_transaction.py',
        'controllers/main.py',
        '__manifest__.py',
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

# Also show the custom_mode selection currently registered and the
# transaction-processing method names present (so we target the right hooks).
print("\n" + "=" * 72)
print("RUNTIME INTROSPECTION")
print("=" * 72)
PP = env['payment.provider']
fld = PP._fields.get('custom_mode')
print("custom_mode selection:", getattr(fld, 'selection', None))

TX = env['payment.transaction']
candidates = [
    '_get_specific_rendering_values', '_get_specific_processing_values',
    '_get_tx_from_notification_data', '_process_notification_data',
    '_process', '_send_payment_request', '_set_pending', '_set_done',
    '_get_default_payment_method_codes',
]
print("\ntransaction/provider methods present:")
for m in candidates:
    print("   tx.%-32s %s" % (m, hasattr(TX, m)))
for m in ('_get_default_payment_method_codes', '_get_compatible_providers'):
    print("   provider.%-26s %s" % (m, hasattr(PP, m)))

print("\n=== END ===\n")
