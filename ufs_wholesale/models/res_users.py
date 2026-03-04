# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    ufs_company_name = fields.Char(
        string="Wholesale Company Name",
        related="partner_id.ufs_company_name",
        readonly=False,
    )
    ufs_fein_taxid = fields.Char(
        string="FEIN / Tax ID",
        related="partner_id.ufs_fein_taxid",
        readonly=False,
    )
    ufs_state_text = fields.Char(
        string="State / Region",
        related="partner_id.ufs_state_text",
        readonly=False,
    )
    ufs_country_text = fields.Char(
        string="Country",
        related="partner_id.ufs_country_text",
        readonly=False,
    )
    ufs_resale_certificate = fields.Binary(
        string="Tax Resale Certificate",
        related="partner_id.ufs_resale_certificate",
        readonly=False,
    )
    ufs_resale_certificate_filename = fields.Char(
        string="Certificate Filename",
        related="partner_id.ufs_resale_certificate_filename",
        readonly=False,
    )
    ufs_wholesale_state = fields.Selection(
        selection=[
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Wholesale Status",
        related="partner_id.ufs_wholesale_state",
        readonly=False,
    )
    ufs_wholesale_approved_by_id = fields.Many2one(
        "res.users",
        string="Approved By",
        related="partner_id.ufs_wholesale_approved_by_id",
        readonly=True,
    )
    ufs_wholesale_approved_on = fields.Datetime(
        string="Approved On",
        related="partner_id.ufs_wholesale_approved_on",
        readonly=True,
    )
    ufs_can_wholesale_shop = fields.Boolean(
        string="Can Buy on Website",
        compute="_compute_ufs_can_wholesale_shop",
    )

    @api.depends("share", "partner_id.ufs_wholesale_state")
    def _compute_ufs_can_wholesale_shop(self):
        for user in self:
            user.ufs_can_wholesale_shop = user._ufs_has_wholesale_access()

    def _ufs_has_wholesale_access(self):
        self.ensure_one()
        return bool(self._is_internal() or self.partner_id.ufs_wholesale_state == "approved")

    def _ufs_send_mail_template(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            return
        for user in self.sudo():
            if user.email:
                template.sudo().send_mail(user.id, force_send=True)

    def action_ufs_set_wholesale_pending(self):
        for user in self.sudo():
            if user._is_internal():
                continue
            user.partner_id.write({
                "ufs_wholesale_state": "pending",
                "ufs_wholesale_approved_by_id": False,
                "ufs_wholesale_approved_on": False,
            })

    def action_ufs_wholesale_approve(self):
        now = fields.Datetime.now()
        approver_id = self.env.user.id
        users_to_welcome = self.env["res.users"]
        for user in self.sudo():
            if user._is_internal():
                continue
            if user.partner_id.ufs_wholesale_state != "approved":
                users_to_welcome |= user
            user.partner_id.write({
                "ufs_wholesale_state": "approved",
                "ufs_wholesale_approved_by_id": approver_id,
                "ufs_wholesale_approved_on": now,
            })
        if users_to_welcome:
            users_to_welcome._ufs_send_mail_template("ufs_wholesale.mail_template_wholesale_welcome")
        return True

    def action_ufs_wholesale_reject(self):
        for user in self.sudo():
            if user._is_internal():
                continue
            user.partner_id.write({
                "ufs_wholesale_state": "rejected",
                "ufs_wholesale_approved_by_id": False,
                "ufs_wholesale_approved_on": False,
            })
        return True

    def action_ufs_send_registration_acknowledgement(self):
        self._ufs_send_mail_template("ufs_wholesale.mail_template_wholesale_signup_ack")
        return True

