# -*- coding: utf-8 -*-

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    def _ufs_wholesale_can_buy(self):
        self.ensure_one()
        user = self.env.user
        if not user or user._is_public():
            return False
        return user._ufs_has_wholesale_access()

    def _get_and_cache_current_pricelist(self):
        """Force a logged-in customer's own UFS pricelist onto the storefront.

        Each customer's pricelist (ufs_customer_pricing) is website-bound but
        deliberately NOT selectable — otherwise it would appear in the public
        pricelist selector for everyone. Because Odoo's standard website
        resolution only considers *selectable* pricelists, the per-customer
        special prices never surfaced on the shop/product pages and the cart
        fell back to the public list price (which is the reported bug).

        Here we let standard resolution run, then override the result with the
        partner's own UFS pricelist when they have one. This makes the shop,
        product pages, and cart all price under the customer's special rules,
        which in turn makes website-originated orders (and their PDFs) correct.
        """
        pricelist = super()._get_and_cache_current_pricelist()
        user = self.env.user
        if not user or user._is_public():
            return pricelist
        ufs_pl = user.partner_id.ufs_pricelist_id
        if ufs_pl and (not pricelist or ufs_pl.id != pricelist.id):
            return ufs_pl
        return pricelist

