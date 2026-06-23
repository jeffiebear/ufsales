# -*- coding: utf-8 -*-
"""
Consolidate fragmented draft purchase orders.

Standard Odoo procurement creates a separate draft PO whenever the
grouping keys differ (procurement group, timing, etc.), so backordered
items for the SAME vendor can land on several separate draft POs. This
adds a daily cron (and a manual action) that merges same-vendor draft
POs into one.

Safety: we MERGE BY REPARENTING LINES, not by summing quantities. Each
purchase.order.line keeps its identity and simply moves to the surviving
PO (line.order_id = target). Because the line records persist, every
procurement link that points at them (stock.move.created_purchase_line_id,
move_dest_ids, etc.) stays valid — no traceability is broken. Empty
source POs are then removed.

Only DRAFT POs are touched (never 'sent'/'purchase'/'done'), and POs are
only merged when they match on every field that would make a merge
ambiguous (vendor, company, currency, picking type, ship-to, terms,
incoterm, fiscal position). Gated behind a setting, default OFF.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def _ufs_consolidate_enabled(self):
        ICP = self.env['ir.config_parameter'].sudo()
        return ICP.get_param('ufs_customizations.consolidate_draft_pos') in ('True', '1', 'true')

    @api.model
    def _ufs_merge_group_key(self, po):
        """Fields that must all match for two draft POs to be safely merged.
        Optional fields are read defensively so this works across editions."""
        def g(name):
            return po[name].id if name in po._fields and po[name] else False
        return (
            po.partner_id.id,
            po.company_id.id,
            po.currency_id.id,
            g('picking_type_id'),
            g('dest_address_id'),
            g('payment_term_id'),
            g('incoterm_id'),
            g('fiscal_position_id'),
        )

    @api.model
    def _ufs_cron_merge_draft_pos(self):
        """Daily: merge same-vendor draft POs into one each. No-op unless
        the consolidation setting is enabled."""
        if not self._ufs_consolidate_enabled():
            _logger.info("ufs PO merge: consolidation disabled — skipping.")
            return
        return self._ufs_merge_draft_pos()

    @api.model
    def _ufs_merge_draft_pos(self):
        """Do the merge. Returns the number of source POs absorbed.
        Callable directly (manual action) regardless of the setting."""
        drafts = self.search([('state', '=', 'draft')], order='date_order, id')
        groups = {}
        for po in drafts:
            groups.setdefault(self._ufs_merge_group_key(po), self.browse())
            groups[self._ufs_merge_group_key(po)] |= po

        absorbed = 0
        for key, pos in groups.items():
            if len(pos) < 2:
                continue
            ordered = pos.sorted(lambda p: (p.date_order or fields.Datetime.now(), p.id))
            target = ordered[0]
            rest = ordered[1:]
            try:
                for src in rest:
                    # Reparent the lines (keeps line identity + procurement links).
                    src.order_line.write({'order_id': target.id})
                    absorbed += 1
                # Remove the now-empty source POs.
                empties = rest.filtered(lambda p: not p.order_line)
                if empties:
                    empties.unlink()
                target.message_post(body=_(
                    "UFS daily PO digest: merged %s draft purchase order(s) "
                    "for %s into this one."
                ) % (len(rest), target.partner_id.display_name))
            except Exception as exc:
                # One bad group shouldn't abort the whole digest.
                _logger.exception(
                    "ufs PO merge: failed merging group for vendor %s: %s",
                    target.partner_id.display_name, exc,
                )
                self.env.cr.rollback()
                continue
            self.env.cr.commit()

        _logger.info("ufs PO merge: absorbed %s source draft PO(s).", absorbed)
        return absorbed

    def action_ufs_merge_draft_pos(self):
        """Manual trigger from the PO list (Action menu). Merges across all
        current draft POs, not just the selected ones, then reloads."""
        self._ufs_merge_draft_pos()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
