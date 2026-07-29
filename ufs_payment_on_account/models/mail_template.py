# -*- coding: utf-8 -*-
"""
Correct the order confirmation subject line for net-terms orders.

THE PROBLEM
===========
Stock Odoo builds the subject of ``sale.mail_template_sale_confirmation``
by asking the TRANSACTION whether it is pending:

    {{ (object.get_portal_last_transaction().state == 'pending')
       and 'Pending Order' or 'Order' }}

while the body of the same template asks the ORDER:

    <t t-if="object.state == 'sale' or (tx_sudo and tx_sudo.state
             in ('done', 'authorized'))">has been confirmed.

For every ordinary provider those two agree, because the transaction
reaching ``done`` is exactly what confirms the order. Pay on Account
breaks the tie deliberately: the order is confirmed while the
transaction stays ``pending``, because with net terms no money has moved
and marking it done would make Odoo post a payment that does not exist
(see ``payment_transaction.py``).

The result was an email headed "Pending Order" whose body said the order
had been confirmed. Confirming the order alone did not fix the
complaint; it only moved it from the body to the subject line.

WHY THIS IS PYTHON AND NOT A DATA FILE
======================================
``sale`` ships that template inside ``<data noupdate="1">``. The flag
lives on the record's ``ir.model.data`` row, so a ``<record>`` in
another module is skipped on upgrade no matter which module declares it,
and no matter whether the upgrade is triggered from the UI or a build.
An earlier attempt to fix this with a plain data record silently did
nothing for exactly that reason.

A ``<function>`` call sidesteps the flag: it is ordinary Python invoked
by the data loader, and the loader re-runs data files on every module
update, so the correction is re-applied if anything ever resets the
template.

The patch is a targeted string replacement rather than a wholesale
rewrite of the subject, so it does not clobber unrelated wording. It is
idempotent, and it deliberately does nothing if the stock condition is
no longer present: a future Odoo version that rewrites this subject
should not be silently patched on a pattern that no longer means what we
think it means.
"""
from odoo import api, models

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)

# The stock condition, and the same test with the order consulted first.
_STOCK_CONDITION = (
    "(object.get_portal_last_transaction().state == 'pending')"
)
_FIXED_CONDITION = (
    "(object.state != 'sale'"
    " and object.get_portal_last_transaction().state == 'pending')"
)


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _ufs_fix_order_confirmation_subject(self):
        """Make the confirmation subject agree with its own body.

        Called from ``data/mail_template_data.xml`` so it runs on install
        and on every subsequent module update.
        """
        template = self.env.ref(
            'sale.mail_template_sale_confirmation', raise_if_not_found=False
        )
        if not template:
            return

        subject = template.subject or ''
        if _FIXED_CONDITION in subject:
            return  # Already corrected.
        if _STOCK_CONDITION not in subject:
            _logger.info(
                "Order confirmation subject does not match the expected "
                "Odoo wording; leaving it untouched."
            )
            return

        template.subject = subject.replace(_STOCK_CONDITION, _FIXED_CONDITION)
        _logger.info(
            "Order confirmation subject patched: confirmed orders are no "
            "longer titled 'Pending Order'."
        )
