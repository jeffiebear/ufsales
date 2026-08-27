# -*- coding: utf-8 -*-
"""
Print vendor-payment checks straight to the Konica.

The standard check flow renders a PDF the user then prints by hand. This
adds a "Print to Konica" button on the payment that renders the same
configured check layout and POSTs it to the print relay instead, exactly
like the Print to Konica buttons on orders, invoices, deliveries and POs.

The guards mirror account_check_printing.do_print_checks: same journal,
draft checks are posted first so their numbers are assigned, and a check
layout must be configured. The relay config (URL, secret, timeout) is the
same ufs_print.* set used everywhere else.

Note: sending checks to a shared office printer means blank check stock
sits loaded in it and anyone who can reach this button can print one.
That is a control decision for UFS, not a technical one; the button rides
the existing ufs_print.enabled master switch so it can be left off until
they decide.
"""
import base64
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    ufs_is_check = fields.Boolean(
        string="Is a printable check",
        compute='_compute_ufs_is_check',
        help="True when this payment uses the Check payment method. Drives "
             "the visibility of the Print to Konica button.",
    )

    @api.depends('payment_method_line_id.code')
    def _compute_ufs_is_check(self):
        for payment in self:
            payment.ufs_is_check = (
                payment.payment_method_line_id.code == 'check_printing'
            )

    def action_ufs_print_checks_konica(self):
        """Render the configured check layout for the selected checks and
        send the PDF to the Konica through the print relay."""
        checks = self.filtered(
            lambda p: p.payment_method_line_id.code == 'check_printing'
        )
        if not checks:
            raise UserError(_("Select one or more check payments to print."))
        if any(p.journal_id != checks[0].journal_id for p in checks):
            raise UserError(_(
                "To print several checks at once they must be on the same "
                "bank journal."
            ))

        # Post any drafts first so their check numbers get assigned, the
        # same thing the standard "Print Checks" action does.
        checks.filtered(lambda p: p.state == 'draft').action_post()

        layout = (
            checks[0].journal_id.bank_check_printing_layout
            or checks[0].company_id.account_check_printing_layout
        )
        if not layout or layout == 'disabled':
            raise UserError(_(
                "Choose a check layout first, under Accounting > "
                "Configuration > Settings > Checks."
            ))
        report = self.env.ref(layout, raise_if_not_found=False)
        if not report:
            raise UserError(_(
                "The configured check layout could not be found. Pick one "
                "in Accounting settings and try again."
            ))

        try:
            pdf_bytes, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report.report_name, res_ids=checks.ids,
            )
        except Exception as exc:
            raise UserError(_(
                "Could not generate the check PDF: %s"
            ) % exc) from exc

        self._ufs_send_checks_to_relay(pdf_bytes, checks)
        checks.write({'is_sent': True})
        for payment in checks:
            payment.message_post(body=_(
                "Check sent to the Konica via the print relay."
            ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Sent to Konica"),
                'message': _("%s check(s) sent to the printer.") % len(checks),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _ufs_send_checks_to_relay(self, pdf_bytes, checks):
        """POST the rendered check PDF to the print relay, reusing the
        ufs_print relay configuration."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('ufs_print.enabled') not in ('True', '1', 'true'):
            raise UserError(_(
                "Konica printing is turned off. Turn it on in "
                "Settings > UFS Printing."
            ))
        url = (ICP.get_param('ufs_print.webhook_url') or '').strip()
        secret = (ICP.get_param('ufs_print.shared_secret') or '').strip()
        if not url or not secret:
            raise UserError(_(
                "Konica printing is not configured. Add the Print Relay "
                "URL and Shared Secret in Settings > UFS Printing."
            ))
        try:
            timeout = int(ICP.get_param('ufs_print.timeout', 20)) or 20
        except (TypeError, ValueError):
            timeout = 20

        payload = {
            'type': 'check',
            'doc_id': checks[0].id,
            'doc_ref': _("%s check(s)") % len(checks),
            'copies': 1,
            'double_sided': False,
            'pdf_base64': base64.b64encode(pdf_bytes).decode('ascii'),
        }
        headers = {'Content-Type': 'application/json', 'X-Print-Secret': secret}
        try:
            resp = requests.post(
                url, data=json.dumps(payload), headers=headers, timeout=timeout,
            )
        except requests.RequestException as exc:
            raise UserError(_(
                "Could not reach the print server. The checks were not "
                "printed.\n\nDetails: %s"
            ) % exc) from exc
        if not (200 <= resp.status_code < 300):
            raise UserError(_(
                "The print server returned an error (HTTP %s). The checks "
                "were not printed.\n\n%s"
            ) % (resp.status_code, (resp.text or '').strip()[:500]))
