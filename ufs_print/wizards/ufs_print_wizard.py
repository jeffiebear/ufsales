# -*- coding: utf-8 -*-
"""
Print-to-Konica wizard.

Opened from the "Print to Konica" header button on the supported
documents. Shows the doc being printed plus per-print controls
(copies + double-sided), then renders the standard report to PDF and
POSTs it to the print-relay webhook.

Payload contract (matches the Jalaram relay shape):

    {
      "type": "sale_order" | "invoice" | "packing_slip" | "purchase_order",
      "doc_id": 123,
      "doc_ref": "S00123",
      "copies": 1,
      "double_sided": true,
      "pdf_base64": "...."
    }

Header: X-Print-Secret: <shared secret>

Print failures raise a UserError (the user clicked Print, they should
know if it didn't work) and are also logged to the document chatter
alongside successes.
"""
import base64
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# model -> (payload type, report xmlid)
_PRINT_MAP = {
    'sale.order':     ('sale_order',     'sale.action_report_saleorder'),
    'account.move':   ('invoice',        'account.account_invoices'),
    'stock.picking':  ('packing_slip',   'stock.action_report_delivery'),
    'purchase.order': ('purchase_order', 'purchase.action_report_purchase_order'),
}


class UfsPrintWizard(models.TransientModel):
    _name = 'ufs.print.wizard'
    _description = 'Print to Konica'

    doc_model = fields.Char(readonly=True)
    doc_id = fields.Integer(readonly=True)
    doc_name = fields.Char(string='Document', readonly=True)
    copies = fields.Integer(string='Copies', default=1, required=True)
    double_sided = fields.Boolean(string='Double-sided', default=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        model = self.env.context.get('active_model')
        res_id = self.env.context.get('active_id')
        if model not in _PRINT_MAP or not res_id:
            raise UserError(_(
                "This document type can't be printed to the Konica."
            ))
        rec = self.env[model].browse(res_id)
        vals.update({
            'doc_model': model,
            'doc_id': res_id,
            'doc_name': rec.display_name,
        })
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            vals['copies'] = int(ICP.get_param('ufs_print.default_copies', 1)) or 1
        except (TypeError, ValueError):
            vals['copies'] = 1
        return vals

    def action_print(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()

        # res.config.settings stores a Boolean config_parameter as the
        # string "True"/"False" (not "1"/"0"), so accept either form.
        if ICP.get_param('ufs_print.enabled') not in ('True', '1', 'true'):
            raise UserError(_(
                "Konica printing is turned off. Turn it on in "
                "Settings → UFS Printing."
            ))
        url = (ICP.get_param('ufs_print.webhook_url') or '').strip()
        secret = (ICP.get_param('ufs_print.shared_secret') or '').strip()
        if not url or not secret:
            raise UserError(_(
                "Konica printing isn't configured yet. Add the Print "
                "Relay URL and Shared Secret in Settings → UFS Printing."
            ))
        try:
            timeout = int(ICP.get_param('ufs_print.timeout', 20)) or 20
        except (TypeError, ValueError):
            timeout = 20

        ptype, report_xmlid = _PRINT_MAP[self.doc_model]
        rec = self.env[self.doc_model].browse(self.doc_id)
        copies = max(1, self.copies or 1)

        # Render the standard report to PDF.
        try:
            pdf_bytes, _content_type = self.env['ir.actions.report']._render_qweb_pdf(
                report_xmlid, res_ids=[self.doc_id],
            )
        except Exception as exc:
            raise UserError(_(
                "Could not generate the PDF for %s: %s"
            ) % (rec.display_name, exc)) from exc

        payload = {
            'type': ptype,
            'doc_id': self.doc_id,
            'doc_ref': rec.display_name,
            'copies': copies,
            'double_sided': bool(self.double_sided),
            'pdf_base64': base64.b64encode(pdf_bytes).decode('ascii'),
        }
        headers = {
            'Content-Type': 'application/json',
            'X-Print-Secret': secret,
        }

        try:
            resp = requests.post(
                url, data=json.dumps(payload), headers=headers, timeout=timeout,
            )
        except requests.RequestException as exc:
            self._ufs_log(rec, ok=False, copies=copies,
                          detail=_("could not reach relay: %s") % exc)
            raise UserError(_(
                "Could not reach the print server. The document was not "
                "printed.\n\nDetails: %s"
            ) % exc) from exc

        ok = 200 <= resp.status_code < 300
        body = (resp.text or '').strip()[:500]
        self._ufs_log(rec, ok=ok, copies=copies,
                      detail=_("HTTP %s %s") % (resp.status_code, body))

        if not ok:
            raise UserError(_(
                "The print server returned an error (HTTP %s). The "
                "document was not printed.\n\n%s"
            ) % (resp.status_code, body))

        return {'type': 'ir.actions.act_window_close'}

    def _ufs_log(self, rec, ok, copies, detail):
        """Post a one-line print attempt to the document chatter."""
        if not hasattr(rec, 'message_post'):
            return
        status = _("sent to printer") if ok else _("PRINT FAILED")
        sides = _("double-sided") if self.double_sided else _("single-sided")
        rec.message_post(body=_(
            "Print to Konica: %s — %s copy(ies), %s. (%s)"
        ) % (status, copies, sides, detail))
