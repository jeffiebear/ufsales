# -*- coding: utf-8 -*-

from odoo import api, models


class UfsalesCatalogSeedHelper(models.AbstractModel):
    _name = "ufsales.catalog.seed.helper"
    _description = "UF Sales Catalog Seed Helper"

    @api.model
    def cleanup_legacy_menus(self):
        """Remove previously seeded website menus from older module revisions."""
        imd = self.env["ir.model.data"].search(
            [
                ("module", "=", "ufsales_catalog_seed"),
                ("model", "=", "website.menu"),
                ("name", "like", "menu_uf_%"),
            ]
        )
        if not imd:
            return True

        menus = self.env["website.menu"].browse(imd.mapped("res_id")).exists()
        if menus:
            menus.unlink()
        imd.unlink()
        return True
