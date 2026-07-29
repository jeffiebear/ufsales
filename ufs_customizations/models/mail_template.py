# -*- coding: utf-8 -*-
"""
Drop the "already paid" sentence from the customer invoice email.

WHAT UFS ASKED FOR
==================
The invoice email should not tell the customer their invoice is already
paid. UFS emails invoices to collect on them, so that branch never
applies to the message they are actually sending, and it reads as
contradictory next to an amount due.

WHY THEY COULD NOT DELETE IT THEMSELVES
=======================================
The sentence is not loose text. Stock Odoo wraps it in a QWeb condition
paired with an else branch:

    <t t-if="object.payment_state in ('paid', 'in_payment')">
        This invoice is already paid.
    </t>
    <t t-else="">
        Please remit payment at your earliest convenience.
        ...
    </t>

The template editor loads QWebPlugin, which shows only one branch of a
pair at a time and treats each QWeb node as unsplittable, so a mouse
selection can never resolve to "just this sentence". That is the "if
statement I can't get past" in the client's report, and it is why their
attempts either did nothing or snapped back on save.

Deleting only the sentence is also the wrong repair. It leaves an empty
t-if, and if that empty inline node is normalised away the t-else is
orphaned, which raises at render time because t-else must directly
follow its t-if. The whole conditional has to go together.

THE EDIT
========
Remove the t-if branch outright and turn its t-else into a positive
t-if on the inverted condition. Behaviour is preserved exactly: the
"remit payment" wording still renders only for invoices that are not
already paid, so a receipt for a settled invoice does not suddenly start
asking for money.

WHY PYTHON AND NOT A DATA FILE
==============================
``account`` declares this template noupdate, and that flag lives on the
record's ir.model.data row, so a <record> from another module is skipped
on upgrade regardless of which module declares it. A <function> is
ordinary Python run by the data loader, which is not subject to the
flag, and data files re-run on each module update.

The patch anchors on the exact stock markup and does nothing at all if
it does not find it, so a future Odoo release that rewrites this
template will be left alone rather than silently mangled. It is
idempotent, and it does not touch any other part of the body, so UFS can
still edit the rest of the email freely in the UI.
"""
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

# Matches the stock paid/unpaid pair: the whole t-if branch plus the
# opening tag of the t-else that follows it. Tolerant of whitespace and
# of either quote style, but still specific to this exact conditional.
_PAID_BRANCH_RE = re.compile(
    r"""<t\s+t-if=(?P<q>["'])\s*object\.payment_state\s+in\s+\(\s*['"]paid['"]\s*,"""
    r"""\s*['"]in_payment['"]\s*\)\s*(?P=q)\s*>"""   # <t t-if="...paid...">
    r""".*?</t>"""                                    # ... branch body ...
    r"""\s*<t\s+t-else=(["'])\2\s*>""",               # <t t-else="">
    re.DOTALL | re.VERBOSE,
)

# The t-else becomes a positive test on the inverse condition.
_REPLACEMENT = (
    '<t t-if="object.payment_state not in (\'paid\', \'in_payment\')">'
)


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.model
    def _ufs_strip_invoice_already_paid(self):
        """Remove the already-paid branch from the invoice email.

        Called from ``data/mail_template_data.xml`` so it runs on install
        and on every subsequent module update.
        """
        template = self.env.ref(
            'account.email_template_edi_invoice', raise_if_not_found=False
        )
        if not template:
            return

        body = template.body_html or ''
        if 'already paid' not in body:
            return  # Already stripped, or Odoo changed the wording.

        new_body, count = _PAID_BRANCH_RE.subn(_REPLACEMENT, body, count=1)
        if not count:
            _logger.warning(
                "Invoice email still contains the already-paid sentence but "
                "not in the expected conditional; leaving it untouched so a "
                "changed template is not corrupted."
            )
            return

        template.body_html = new_body
        _logger.info("Invoice email: removed the already-paid branch.")
