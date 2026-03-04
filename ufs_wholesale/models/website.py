# -*- coding: utf-8 -*-

from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _ufs_wholesale_can_buy(self):
        self.ensure_one()
        user = self.env.user
        if not user or user._is_public():
            return False
        return user._ufs_has_wholesale_access()

