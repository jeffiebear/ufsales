# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ufs_step1_invoice_count = fields.Integer(compute="_compute_ufs_step1_invoice_count")

    def _compute_ufs_step1_invoice_count(self):
        groups = self.env["ufs.step1.invoice"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"])
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.ufs_step1_invoice_count = counts.get(partner.id, 0)

    def action_view_ufs_step1_invoices(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("ufs_step1_history.action_ufs_step1_invoice")
        action["domain"] = [("partner_id", "=", self.id)]
        action["context"] = {"default_partner_id": self.id, "search_default_group_year": 1}
        return action
