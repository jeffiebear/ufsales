# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Restricted like the other non-public employee fields: readers without HR
    # rights go through hr.employee.public, which does not carry it. The sale
    # order reads it with sudo().
    ufs_commission_rate = fields.Float(
        string="Commission % of Margin",
        groups="hr.group_hr_user",
        help="Percent of an order's margin this employee earns as sales rep. "
             "Copied onto each order when the rep is set, so changing it here "
             "only affects orders from then on.",
    )
