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
    import_customers = fields.Boolean(default=True, string="Import Customers")
    import_products = fields.Boolean(default=True, string="Import Products")
    import_warehouse = fields.Boolean(default=True, string="Import Warehouse / Inventory")
    import_po_history = fields.Boolean(default=False, string="Import PO History (inert)")

    vendors_file = fields.Binary(string="Vendors CSV (optional)")
    vendors_filename = fields.Char()
    customers_file = fields.Binary(string="Customers CSV (optional)")
    customers_filename = fields.Char()
    products_file = fields.Binary(string="Product Inventory CSV (optional)")
    products_filename = fields.Char()
    warehouse_file = fields.Binary(string="Warehouse CSV (optional)")
    warehouse_filename = fields.Char()
    po_summary_file = fields.Binary(string="PO Summary CSV (optional)")
    po_summary_filename = fields.Char()
    po_detail_file = fields.Binary(string="PO Detail CSV (optional)")
    po_detail_filename = fields.Char()

    log = fields.Text(string="Log", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")],
        default="draft",
    )

    def action_import(self):
        self.ensure_one()
        if not (
            self.import_vendors or self.import_customers
            or self.import_products or self.import_warehouse
            or self.import_po_history
        ):
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
        # products before warehouse (for stock/orderpoints). Customers
        # are independent and run first so later steps that rely on the
        # partner table (none today) are safe.
        if self.import_customers:
            _run("Customers", importer.run_customer_import, self.customers_file)
        if self.import_vendors:
            _run("Vendors", importer.run_vendor_import, self.vendors_file)
        if self.import_products:
            _run("Products", importer.run_product_import, self.products_file)
        if self.import_warehouse:
            _run("Warehouse", importer.run_warehouse_import, self.warehouse_file)
        if self.import_po_history:
            try:
                result = importer.run_po_history_import(
                    self.po_summary_file, self.po_detail_file,
                )
                lines.append("PO History: %s" % ", ".join(
                    "%s=%s" % (k, v) for k, v in result.items()
                ))
            except Exception as e:
                _logger.exception("PO History failed")
                lines.append("PO History: ERROR — %s" % e)

        self.write({"log": "\n".join(lines), "state": "done"})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
