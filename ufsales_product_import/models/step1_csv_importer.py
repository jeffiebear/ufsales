# -*- coding: utf-8 -*-
"""STEP1 CSV importers for vendors, products (inventory info) and
per-warehouse stock. Accompanies the JSON-based website catalog
importer in `product_importer.py` — the two are complementary.

Flow:
    1. vendors.csv              → res.partner (supplier_rank=1)
    2. product_inventory_info.csv → product.template + product.supplierinfo
    3. warehouse.csv            → stock.quant + stock.warehouse.orderpoint
    4. Price tiers (from products file) → UFS Quantity Brackets pricelist

Each step can run independently via the wizard.
"""
import base64
import csv
import io
import logging
from datetime import datetime
from pathlib import Path

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)


_DEFAULT_VENDORS_CSV = "data/vendors.csv"
_DEFAULT_PRODUCTS_CSV = "data/product_inventory_info.csv"
_DEFAULT_WAREHOUSE_CSV = "data/warehouse.csv"
_BRACKET_PRICELIST_NAME = "UFS Quantity Brackets"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _s(v):
    return (v or "").strip()


def _yesno(v):
    return _s(v).upper() in ("Y", "YES", "TRUE", "1")


def _to_float(v):
    s = _s(v)
    if not s:
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


def _to_int(v):
    s = _s(v)
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _to_date(v):
    s = _s(v)
    if not s:
        return False
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return False


def _normalize_item_code(v):
    """STEP1 sometimes exports ItemCode with a leading `[` artifact."""
    s = _s(v)
    return s.lstrip("[").strip() if s else s


def _decode_csv(raw):
    """Decode a raw bytes payload from one of several common encodings."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UserError(_("Could not decode CSV file — unknown encoding."))


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------
class UfsalesStep1CsvImporter(models.AbstractModel):
    _name = "ufsales.step1.csv.importer"
    _description = "UF Sales STEP1 CSV Importer"

    # ----- file loading ---------------------------------------------------
    @api.model
    def _module_dir(self):
        path = get_module_path("ufsales_product_import", display_warning=False)
        if path:
            return Path(path).resolve()
        return Path(__file__).resolve().parents[1]

    @api.model
    def _read_csv(self, source, default_relative):
        """Accept a base64 upload, an absolute path, or fall back to the
        bundled CSV. Returns a list of dict rows."""
        raw = None
        if source:
            if isinstance(source, bytes):
                raw = source
            else:
                try:
                    raw = base64.b64decode(source)
                except (ValueError, TypeError):
                    raw = None
        if raw is None:
            path = self._module_dir() / default_relative
            if not path.exists():
                raise UserError(_(
                    "Bundled CSV not found: %s. Upload one via the wizard."
                ) % path)
            raw = path.read_bytes()
        text = _decode_csv(raw)
        return list(csv.DictReader(io.StringIO(text)))

    # ================================================================
    # 1. Vendors
    # ================================================================
    @api.model
    def run_vendor_import(self, csv_source=None):
        rows = self._read_csv(csv_source, _DEFAULT_VENDORS_CSV)
        Partner = self.env["res.partner"].sudo().with_context(active_test=False)
        if not rows:
            raise UserError(_("Vendor CSV is empty."))
        if "VendorAcct" not in (rows[0].keys() if rows else ()):
            raise UserError(_(
                "This doesn't look like a Vendors export (no VendorAcct column)."
            ))

        by_acct = {
            p.ufs_step1_vendor_acct: p
            for p in Partner.search([("ufs_step1_vendor_acct", "!=", False)])
        }
        created = updated = skipped = 0
        for row in rows:
            acct = _s(row.get("VendorAcct"))
            name = _s(row.get("VendorName"))
            if not acct or not name:
                skipped += 1
                continue
            vals = self._vendor_vals(row)
            partner = by_acct.get(acct)
            if partner:
                partner.write(vals)
                updated += 1
            else:
                vals["ufs_step1_vendor_acct"] = acct
                partner = Partner.create(vals)
                by_acct[acct] = partner
                created += 1
        _logger.info(
            "UFS vendor import: %s created, %s updated, %s skipped",
            created, updated, skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    @api.model
    def _vendor_vals(self, row):
        # State and country are free-text in STEP1; resolve to records
        # where possible, otherwise leave blank.
        state = self._find_state(_s(row.get("State")))
        country = state.country_id if state else self._find_country("US")
        vals = {
            "name": _s(row.get("VendorName")),
            "company_type": "company",
            "supplier_rank": 1,
            "customer_rank": 0,
            "ref": _s(row.get("VendorAcct")) or False,
            "street": _s(row.get("Address1")) or False,
            "street2": _s(row.get("Address2")) or False,
            "city": _s(row.get("City")) or False,
            "zip": _s(row.get("Zip")) or False,
            "phone": _s(row.get("OfficePhone")) or False,
            "email": _s(row.get("OfficeContactEmailAddress"))
                     or _s(row.get("POContactEmailAddress"))
                     or False,
            "website": _s(row.get("WebAddress")) or False,
            "active": not _yesno(row.get("ObsoleteFlag")),
            "ufs_step1_vendor_id": _s(row.get("VendorID")) or False,
            "ufs_vendor_group_code": _s(row.get("VendorGroupCode")) or False,
            "ufs_carrier": _s(row.get("Carrier")) or False,
        }
        if state:
            vals["state_id"] = state.id
        if country:
            vals["country_id"] = country.id
        return vals

    @api.model
    def _find_state(self, code_or_name):
        if not code_or_name:
            return self.env["res.country.state"].browse()
        State = self.env["res.country.state"].sudo()
        us = self._find_country("US")
        domain = []
        if us:
            domain.append(("country_id", "=", us.id))
        # Try 2-letter code first, then name
        rec = State.search(domain + [("code", "=", code_or_name.upper())], limit=1)
        if not rec:
            rec = State.search(domain + [("name", "=ilike", code_or_name)], limit=1)
        return rec

    @api.model
    def _find_country(self, code):
        if not code:
            return self.env["res.country"].browse()
        return self.env["res.country"].sudo().search(
            [("code", "=", code.upper())], limit=1,
        )

    # ================================================================
    # 2. Products (inventory info)
    # ================================================================
    @api.model
    def run_product_import(self, csv_source=None):
        rows = self._read_csv(csv_source, _DEFAULT_PRODUCTS_CSV)
        if not rows or "ItemCode" not in (rows[0].keys() if rows else ()):
            raise UserError(_(
                "This doesn't look like a ProductInventoryInfo export."
            ))
        Template = self.env["product.template"].sudo().with_context(active_test=False)

        # Pre-cache vendor partners by VendorAcct
        vendor_by_acct = {
            p.ufs_step1_vendor_acct: p
            for p in self.env["res.partner"].sudo().search([
                ("ufs_step1_vendor_acct", "!=", False),
            ])
        }

        # Pre-cache products by the two possible keys
        has_item_code_field = "ufs_step1_item_code" in Template._fields
        existing_by_item = {}
        if has_item_code_field:
            for t in Template.search([("ufs_step1_item_code", "!=", False)]):
                existing_by_item[t.ufs_step1_item_code] = t
        existing_by_default = {
            t.default_code: t
            for t in Template.search([("default_code", "!=", False)])
        }

        placeholder_image = self.env["ufsales.product.importer"]._get_fallback_product_image()

        created = updated = skipped = 0
        bracket_items = []  # (template, tier_vals) collected for pricelist
        for row in rows:
            sku = _normalize_item_code(row.get("ItemCode"))
            if not sku:
                skipped += 1
                continue
            template = existing_by_item.get(sku) or existing_by_default.get(sku)
            is_new = not template
            vals = self._product_vals(row, has_item_code_field)

            if is_new:
                vals["default_code"] = sku
                if has_item_code_field:
                    vals["ufs_step1_item_code"] = sku
                # Never publish new imports to the website
                if "website_published" in Template._fields:
                    vals["website_published"] = False
                if "is_published" in Template._fields:
                    vals["is_published"] = False
                if placeholder_image and "image_1920" in Template._fields:
                    vals["image_1920"] = placeholder_image
                template = Template.create(vals)
                created += 1
            else:
                # Do NOT touch publish flag or existing images — preserve
                # whatever the operator or the JSON importer has set.
                template.write(vals)
                updated += 1

            # Supplier info (primary + alt)
            self._sync_supplier_info(template, row, vendor_by_acct)
            # Collect tiered pricing for the bracket pricelist
            tier_vals = self._product_tier_items(row, template)
            if tier_vals:
                bracket_items.append((template, tier_vals))

        # Barcode uniqueness note: if a clash happens Odoo raises; we let
        # the row-level try/except in the wizard surface it.

        if bracket_items:
            self._sync_bracket_pricelist(bracket_items)

        _logger.info(
            "UFS product import: %s created, %s updated, %s skipped",
            created, updated, skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    @api.model
    def _product_vals(self, row, has_item_code_field):
        Template = self.env["product.template"]
        fields_map = Template._fields
        name = _s(row.get("ItemDescription")) or _normalize_item_code(row.get("ItemCode"))
        ext_desc = _s(row.get("ItemExtendedDescription"))
        # Pick a cost — prefer LastUnitCost, fall back to AveUnitCost/StdUnitCost.
        cost = (_to_float(row.get("LastUnitCost"))
                or _to_float(row.get("AveUnitCost"))
                or _to_float(row.get("StdUnitCost")))
        uom = self.env["ufsales.product.importer"]._ensure_uom(
            row.get("StockUnit") or row.get("PriceUnit"),
            {"uoms_created": 0},
        )
        vals = {
            "name": name,
            "list_price": _to_float(row.get("ListPrice")),
            "standard_price": cost,
            "sale_ok": True,
            "purchase_ok": True,
            "weight": _to_float(row.get("StockUnitShipWgt")),
            "volume": _to_float(row.get("StockUnitShipCubes")),
            "ufs_bin_number": False,  # populated from warehouse.csv
            "ufs_stock_class": _s(row.get("StockClass")) or False,
            "ufs_sales_class_code": _s(row.get("SalesClass")) or False,
            "ufs_price_unit": _s(row.get("PriceUnit")) or False,
            "ufs_stock_unit": _s(row.get("StockUnit")) or False,
            "ufs_purch_unit": _s(row.get("PurchUnit")) or False,
            "ufs_msds_code": _s(row.get("MSDSCode")) or False,
            "ufs_hazmat_code": _s(row.get("HazMatCode")) or False,
            "ufs_hazmat": _yesno(row.get("HazMatFlag")),
            "ufs_is_obsolete": _yesno(row.get("ObsoleteFlag")),
            "ufs_step1_item_id": _s(row.get("ItemID")) or False,
        }
        # Barcode: prefer UPCCode, else SupplierUPCCode
        upc = _s(row.get("UPCCode")) or _s(row.get("SupplierUPCCode"))
        if upc and "barcode" in fields_map:
            vals["barcode"] = upc
        # Description
        if ext_desc and "description_sale" in fields_map:
            vals["description_sale"] = ext_desc
        # UoM (purchase + stock)
        if uom:
            if "uom_id" in fields_map:
                vals["uom_id"] = uom.id
            if "uom_po_id" in fields_map:
                vals["uom_po_id"] = uom.id
        # Product type — storable (Odoo 19 uses `is_storable` on consu)
        if "type" in fields_map:
            vals["type"] = "consu"
        if "is_storable" in fields_map:
            vals["is_storable"] = True
        # Obsolete → archived
        if _yesno(row.get("ObsoleteFlag")):
            vals["active"] = False
        return vals

    @api.model
    def _sync_supplier_info(self, template, row, vendor_by_acct):
        """Upsert product.supplierinfo rows for the primary and alt vendor."""
        Seller = self.env["product.supplierinfo"].sudo()
        # Odoo 17+ uses `partner_id` + `product_tmpl_id` + `product_code`
        # + `price` + `min_qty` + `delay`.
        pairs = [
            (row.get("SupplierAcct"), row.get("SupplierPartNum")),
            (row.get("AltSupplierAcct"), row.get("AltSupplierPartNum")),
        ]
        kept = Seller.browse()
        for acct, part in pairs:
            acct = _s(acct)
            if not acct or acct == "0":
                continue
            vendor = vendor_by_acct.get(acct)
            if not vendor:
                continue
            vals = {
                "product_tmpl_id": template.id,
                "partner_id": vendor.id,
                "product_code": _s(part) or False,
                "price": _to_float(row.get("LastPOCost")) or _to_float(row.get("LastUnitCost")),
                "min_qty": 1.0,
                "delay": 0,
            }
            existing = Seller.search([
                ("product_tmpl_id", "=", template.id),
                ("partner_id", "=", vendor.id),
            ], limit=1)
            if existing:
                existing.write(vals)
                kept |= existing
            else:
                kept |= Seller.create(vals)
        # Clean up old imported supplierinfo that is no longer listed.
        stale = Seller.search([
            ("product_tmpl_id", "=", template.id),
        ]) - kept
        # Only drop rows that carry a STEP1 vendor (don't nuke manually-
        # added sellers).
        stale = stale.filtered(lambda s: s.partner_id.ufs_step1_vendor_acct)
        if stale:
            stale.unlink()

    @api.model
    def _product_tier_items(self, row, template):
        """Return a list of vals for product.pricelist.item rows covering
        quantity brackets (Price2/MinQty2 … Price8/MinQty8)."""
        items = []
        for n in range(2, 9):
            price = _to_float(row.get("Price%d" % n))
            min_qty = _to_float(row.get("MinQty%d" % n))
            if price <= 0 or min_qty <= 1:
                continue
            items.append({
                "min_quantity": min_qty,
                "fixed_price": price,
                "product_id": template.product_variant_id.id if len(template.product_variant_ids) == 1 else False,
                "product_tmpl_id": template.id,
            })
        return items

    @api.model
    def _sync_bracket_pricelist(self, bracket_items):
        """Populate a shared 'UFS Quantity Brackets' pricelist with one
        fixed-price item per (product, bracket tier)."""
        Pricelist = self.env["product.pricelist"].sudo()
        Item = self.env["product.pricelist.item"].sudo()
        pricelist = Pricelist.search([
            ("name", "=", _BRACKET_PRICELIST_NAME),
            ("company_id", "in", (False, self.env.company.id)),
        ], limit=1)
        if not pricelist:
            pricelist = Pricelist.create({
                "name": _BRACKET_PRICELIST_NAME,
                "currency_id": self.env.company.currency_id.id,
                "company_id": self.env.company.id,
            })
        # Tag all existing items so we can prune stale ones for re-imports.
        tmpl_ids = {t.id for t, _ in bracket_items}
        existing = Item.search([
            ("pricelist_id", "=", pricelist.id),
            ("product_tmpl_id", "in", list(tmpl_ids)),
        ])
        if existing:
            existing.unlink()
        for template, tier_list in bracket_items:
            for tv in tier_list:
                vals = dict(tv)
                vals.update({
                    "pricelist_id": pricelist.id,
                    "applied_on": "0_product_variant" if vals.get("product_id") else "1_product",
                    "compute_price": "fixed",
                })
                if not vals.get("product_id"):
                    vals.pop("product_id", None)
                Item.create(vals)
        return pricelist

    # ================================================================
    # 3. Warehouse / stock
    # ================================================================
    @api.model
    def run_warehouse_import(self, csv_source=None):
        rows = self._read_csv(csv_source, _DEFAULT_WAREHOUSE_CSV)
        if not rows or "ItemCode" not in (rows[0].keys() if rows else ()):
            raise UserError(_(
                "This doesn't look like a Warehouse export."
            ))
        Template = self.env["product.template"].sudo().with_context(active_test=False)
        Quant = self.env["stock.quant"].sudo()
        OrderPoint = self.env["stock.warehouse.orderpoint"].sudo()
        has_item_code_field = "ufs_step1_item_code" in Template._fields

        products_by_code = {}
        for t in Template.search([]):
            if t.default_code:
                products_by_code[t.default_code] = t
        if has_item_code_field:
            for t in Template.search([("ufs_step1_item_code", "!=", False)]):
                products_by_code.setdefault(t.ufs_step1_item_code, t)

        updated = skipped = 0
        by_wh_code = {}
        for row in rows:
            sku = _normalize_item_code(row.get("ItemCode"))
            wh_code = _s(row.get("WHCode")).lstrip("*") or "WH"
            if not sku:
                skipped += 1
                continue
            template = products_by_code.get(sku)
            if not template:
                skipped += 1
                continue
            warehouse = by_wh_code.get(wh_code) or self._ensure_warehouse(
                wh_code, _s(row.get("WHDescription")),
            )
            by_wh_code[wh_code] = warehouse

            # Bin number -> store on template (single-warehouse assumption)
            bin_no = _s(row.get("BinNumber"))
            if bin_no and not template.ufs_bin_number:
                template.ufs_bin_number = bin_no

            # Stock quant: set on-hand in the warehouse's internal stock location
            on_hand = _to_float(row.get("StockOnHand"))
            if on_hand and template.product_variant_ids:
                variant = template.product_variant_id
                self._apply_on_hand(variant, warehouse, on_hand)

            # Reorder rule
            reorder_pt = _to_float(row.get("ReorderPoint"))
            line_pt = _to_float(row.get("LinePoint"))
            reorder_qty = _to_float(row.get("ReorderQty"))
            if (reorder_pt or line_pt or reorder_qty) and template.product_variant_ids:
                variant = template.product_variant_id
                rule = OrderPoint.search([
                    ("product_id", "=", variant.id),
                    ("warehouse_id", "=", warehouse.id),
                ], limit=1)
                vals = {
                    "product_id": variant.id,
                    "warehouse_id": warehouse.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "product_min_qty": reorder_pt,
                    "product_max_qty": line_pt or (reorder_pt + reorder_qty),
                    "qty_to_order_manual": reorder_qty or 0.0,
                }
                if rule:
                    rule.write(vals)
                else:
                    OrderPoint.create(vals)
            updated += 1

        _logger.info(
            "UFS warehouse import: %s products touched, %s skipped",
            updated, skipped,
        )
        return {"updated": updated, "skipped": skipped}

    @api.model
    def _ensure_warehouse(self, wh_code, wh_description):
        Warehouse = self.env["stock.warehouse"].sudo()
        wh = Warehouse.search([("ufs_step1_wh_code", "=", wh_code)], limit=1)
        if wh:
            return wh
        # Use the first existing warehouse by default (WH) for *MAIN,
        # rather than creating a duplicate.
        default = Warehouse.search([], order="id", limit=1)
        if default and wh_code.upper() in ("MAIN", "WH"):
            default.write({"ufs_step1_wh_code": wh_code})
            return default
        return Warehouse.create({
            "name": wh_description or wh_code,
            "code": wh_code[:5].upper() or "WH",
            "ufs_step1_wh_code": wh_code,
        })

    @api.model
    def _apply_on_hand(self, variant, warehouse, qty):
        """Set the on-hand quantity at the warehouse's main stock location
        to `qty`, using Odoo's inventory-adjustment quant helper."""
        Quant = self.env["stock.quant"].sudo()
        location = warehouse.lot_stock_id
        quant = Quant.with_context(inventory_mode=True).search([
            ("product_id", "=", variant.id),
            ("location_id", "=", location.id),
        ], limit=1)
        if quant:
            quant.with_context(inventory_mode=True).write({
                "inventory_quantity": qty,
            })
            quant.with_context(inventory_mode=True).action_apply_inventory()
        else:
            new_quant = Quant.with_context(inventory_mode=True).create({
                "product_id": variant.id,
                "location_id": location.id,
                "inventory_quantity": qty,
            })
            new_quant.with_context(inventory_mode=True).action_apply_inventory()
