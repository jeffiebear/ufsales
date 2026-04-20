# -*- coding: utf-8 -*-
"""Wizard that drives the three STEP1 CSV importers.

If you leave a file field empty, the importer falls back to the CSV
bundled with the module in `data/`.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class UfsalesStep1ImportWizard(models.TransientModel):
    _name = "ufsales.step1.import.wizard"
    _description = "UF Sales STEP1 Import Wizard"

    import_vendors = fields.Boolean(default=True, string="Import Vendors")
    import_products = fields.Boolean(default=True, string="Import Products")
    import_warehouse = fields.Boolean(default=True, string="Import Warehouse / Inventory")

    vendors_file = fields.Binary(string="Vendors CSV (optional)")
    vendors_filename = fields.Char()
    products_file = fields.Binary(string="Product Inventory CSV (optional)")
    products_filename = fields.Char()
    warehouse_file = fields.Binary(string="Warehouse CSV (optional)")
    warehouse_filename = fields.Char()

    log = fields.Text(string="Log", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")],
        default="draft",
    )

    def action_import(self):
        self.ensure_one()
        if not (self.import_vendors or self.import_products or self.import_warehouse):
            raise UserError(_("Pick at least one import step."))
        importer = self.env["ufsales.step1.csv.importer"]
        lines = []

        def _run(label, fn, source):
            try:
                result = fn(source)
                lines.append("%s: %s" % (label, ", ".join(
                    "%s=%s" % (k, v) for k, v in result.items()
                )))
            except Exception as e:
                _logger.exception("%s failed", label)
                lines.append("%s: ERROR — %s" % (label, e))

        # Order matters: vendors before products (for supplierinfo),
        # products before warehouse (for stock/orderpoints).
        if self.import_vendors:
            _run("Vendors", importer.run_vendor_import, self.vendors_file)
        if self.import_products:
            _run("Products", importer.run_product_import, self.products_file)
        if self.import_warehouse:
            _run("Warehouse", importer.run_warehouse_import, self.warehouse_file)

        self.write({"log": "\n".join(lines), "state": "done"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
