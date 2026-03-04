# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ufs_company_name = fields.Char(string="Wholesale Company Name")
    ufs_fein_taxid = fields.Char(string="FEIN / Tax ID")
    ufs_state_text = fields.Char(string="State / Region")
    ufs_country_text = fields.Char(string="Country")
    ufs_resale_certificate = fields.Binary(
        string="Tax Resale Certificate",
        attachment=True,
    )
    ufs_resale_certificate_filename = fields.Char(string="Certificate Filename")
    ufs_wholesale_state = fields.Selection(
        selection=[
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Wholesale Status",
        default="approved",
        required=True,
    )
    ufs_wholesale_approved_by_id = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
    )
    ufs_wholesale_approved_on = fields.Datetime(
        string="Approved On",
        readonly=True,
    )

