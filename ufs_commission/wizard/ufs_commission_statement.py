# -*- coding: utf-8 -*-
"""
Commission statement: one sales rep, one period, printable.

Lists the rep's confirmed orders whose order date falls in the period
(in the user's timezone, the same way the Commissions pivot groups by
month) with sales, margin, rate and commission, and the totals.
"""
from datetime import datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class UfsCommissionStatement(models.TransientModel):
    _name = "ufs.commission.statement"
    _description = "Commission Statement"

    employee_id = fields.Many2one("hr.employee", string="Sales Rep", required=True)
    period = fields.Selection(
        [("this_month", "This month"), ("last_month", "Last month"), ("custom", "Other dates")],
        default="this_month", required=True,
    )
    date_from = fields.Date("From", required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        "To", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1) + relativedelta(months=1, days=-1),
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.onchange("period")
    def _onchange_period(self):
        first = fields.Date.context_today(self).replace(day=1)
        if self.period == "this_month":
            self.date_from, self.date_to = first, first + relativedelta(months=1, days=-1)
        elif self.period == "last_month":
            self.date_from, self.date_to = first - relativedelta(months=1), first - timedelta(days=1)

    def _get_orders(self):
        """Confirmed orders of the rep with an order date inside the period (user timezone)."""
        self.ensure_one()
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")

        def to_utc(day):
            return tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

        return self.env["sale.order"].search([
            ("state", "=", "sale"),
            ("company_id", "=", self.company_id.id),
            ("ufs_sales_rep_id", "=", self.employee_id.id),
            ("date_order", ">=", to_utc(self.date_from)),
            ("date_order", "<", to_utc(self.date_to + timedelta(days=1))),
        ], order="date_order, id")

    def _get_totals(self, orders):
        return {
            "sales": sum(orders.mapped("amount_untaxed")),
            "margin": sum(orders.mapped("margin")),
            "commission": sum(orders.mapped("ufs_commission_amount")),
        }

    def action_print(self):
        self.ensure_one()
        return self.env.ref("ufs_commission.action_report_commission_statement").report_action(self)

    def action_view_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("ufs_commission.action_ufs_commission_orders")
        action["domain"] = [("id", "in", self._get_orders().ids)]
        action["view_mode"] = "list,form"
        action["views"] = [(self.env.ref("ufs_commission.view_ufs_commission_order_list").id, "list"), (False, "form")]
        return action
