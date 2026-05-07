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
_DEFAULT_CUSTOMERS_CSV = "data/customers.csv"
_DEFAULT_PRODUCTS_CSV = "data/product_inventory_info.csv"
_DEFAULT_WAREHOUSE_CSV = "data/warehouse.csv"
_DEFAULT_PO_SUMMARY_CSV = "data/po_summary.csv"
_DEFAULT_PO_DETAIL_CSV = "data/po_detail.csv"
_BRACKET_PRICELIST_NAME = "UFS Quantity Brackets"
_PO_COMMIT_BATCH = 500


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

        def _norm(s):
            return (s or "").strip().lower()
        by_name = {}
        by_email = {}
        for p in Partner.search([
            ("supplier_rank", ">", 0),
            ("parent_id", "=", False),
        ]):
            if p.name:
                by_name.setdefault(_norm(p.name), p)
            if p.email:
                by_email.setdefault(_norm(p.email), p)

        created = updated = skipped = matched_by_fallback = 0
        for row in rows:
            acct = _s(row.get("VendorAcct"))
            name = _s(row.get("VendorName"))
            if not acct or not name:
                skipped += 1
                continue
            vals = self._vendor_vals(row)
            partner = by_acct.get(acct)
            if not partner:
                email_key = _norm(
                    _s(row.get("OfficeContactEmailAddress"))
                    or _s(row.get("POContactEmailAddress"))
                )
                partner = by_name.get(_norm(name))
                if not partner and email_key:
                    partner = by_email.get(email_key)
                if partner:
                    matched_by_fallback += 1
            if partner:
                vals["ufs_step1_vendor_acct"] = acct
                partner.write(vals)
                by_acct[acct] = partner
                by_name.setdefault(_norm(partner.name), partner)
                if partner.email:
                    by_email.setdefault(_norm(partner.email), partner)
                updated += 1
            else:
                vals["ufs_step1_vendor_acct"] = acct
                partner = Partner.create(vals)
                by_acct[acct] = partner
                by_name.setdefault(_norm(partner.name), partner)
                if partner.email:
                    by_email.setdefault(_norm(partner.email), partner)
                created += 1
        _logger.info(
            "UFS vendor import: %s created, %s updated "
            "(%s matched by name/email), %s skipped",
            created, updated, matched_by_fallback, skipped,
        )
        return {
            "created": created,
            "updated": updated,
            "matched_by_name_or_email": matched_by_fallback,
            "skipped": skipped,
        }

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
    # 1b. Customers
    # ================================================================
    @api.model
    def run_customer_import(self, csv_source=None):
        rows = self._read_csv(csv_source, _DEFAULT_CUSTOMERS_CSV)
        if not rows or "CustAcct" not in (rows[0].keys() if rows else ()):
            raise UserError(_(
                "This doesn't look like a Customer export (no CustAcct column)."
            ))
        Partner = self.env["res.partner"].sudo().with_context(active_test=False)

        by_acct = {
            p.ufs_step1_cust_acct: p
            for p in Partner.search([("ufs_step1_cust_acct", "!=", False)])
        }
        # Fallback caches: existing partners keyed on a normalized name
        # and email. Populated once and mutated as we go so repeated
        # imports don't create duplicates.
        def _norm(s):
            return (s or "").strip().lower()
        by_name = {}
        by_email = {}
        for p in Partner.search([
            ("customer_rank", ">", 0),
            ("parent_id", "=", False),
        ]):
            if p.name:
                by_name.setdefault(_norm(p.name), p)
            if p.email:
                by_email.setdefault(_norm(p.email), p)

        created = updated = skipped = ship_created = matched_by_fallback = 0
        for row in rows:
            acct = _s(row.get("CustAcct"))
            # STEP1 exports carry '*' / '^' prefixes for flagged accounts;
            # keep them as the canonical key so ufs_customer_pricing matches.
            name = _s(row.get("CustomerName"))
            if not acct or not name:
                skipped += 1
                continue
            vals = self._customer_vals(row)
            partner = by_acct.get(acct)
            if not partner:
                # No acct match — try to adopt an existing Odoo partner by
                # name, then by email. Stamp ufs_step1_cust_acct so the
                # next run hits the fast path.
                email_key = _norm(
                    _s(row.get("OfficeContactEmailAddress"))
                    or _s(row.get("SalesContactEmailAddress"))
                    or _s(row.get("ARContactEmailAddress"))
                )
                partner = by_name.get(_norm(name))
                if not partner and email_key:
                    partner = by_email.get(email_key)
                if partner:
                    matched_by_fallback += 1
            if partner:
                vals["ufs_step1_cust_acct"] = acct
                partner.write(vals)
                by_acct[acct] = partner
                by_name.setdefault(_norm(partner.name), partner)
                if partner.email:
                    by_email.setdefault(_norm(partner.email), partner)
                updated += 1
            else:
                vals["ufs_step1_cust_acct"] = acct
                partner = Partner.create(vals)
                by_acct[acct] = partner
                by_name.setdefault(_norm(partner.name), partner)
                if partner.email:
                    by_email.setdefault(_norm(partner.email), partner)
                created += 1

            # Primary ShipTo → child partner with type='delivery'
            if self._has_primary_shipto(row):
                if self._upsert_primary_shipto(partner, row):
                    ship_created += 1

        _logger.info(
            "UFS customer import: %s created, %s updated "
            "(%s matched by name/email), %s skipped, %s shiptos",
            created, updated, matched_by_fallback, skipped, ship_created,
        )
        return {
            "created": created,
            "updated": updated,
            "matched_by_name_or_email": matched_by_fallback,
            "skipped": skipped,
            "shiptos": ship_created,
        }

    @api.model
    def _customer_vals(self, row):
        state = self._find_state(_s(row.get("State")))
        country = state.country_id if state else self._find_country("US")

        # Build comments block
        comments = [
            _s(row.get(k))
            for k in ("Comments1", "Comments2", "Comments3")
            if _s(row.get(k))
        ]
        comments_text = "\n".join(comments) if comments else False

        # Terms: STEP1 stores a code like "N10" / "NET30" in free text.
        # Resolve to an account.payment.term when one matches by name,
        # otherwise stash in ufs_terms_text.
        terms_text = _s(row.get("Terms"))
        payment_term = self._find_payment_term(terms_text)

        # Default Pricing Scheme lives in ufs_customer_pricing; feed
        # CustPriceOpt into it only when the field exists.
        pricing_scheme = _s(row.get("CustPriceOpt"))

        # Primary email picks the first non-empty from office→sales→AR.
        email = (
            _s(row.get("OfficeContactEmailAddress"))
            or _s(row.get("SalesContactEmailAddress"))
            or _s(row.get("ARContactEmailAddress"))
            or False
        )
        contact_name = " ".join(filter(None, [
            _s(row.get("OfficeContactFirstName")),
            _s(row.get("OfficeContactLastName")),
        ])) or False

        vals = {
            "name": _s(row.get("CustomerName")),
            "company_type": "company",
            "customer_rank": 1,
            "supplier_rank": 0,
            "ref": _s(row.get("CustAcct")) or False,
            "street": _s(row.get("Address1")) or False,
            "street2": _s(row.get("Address2")) or False,
            "city": _s(row.get("City")) or False,
            "zip": _s(row.get("Zip")) or False,
            "phone": _s(row.get("OfficePhone")) or False,
            "email": email,
            "website": _s(row.get("WebAddress")) or False,
            "comment": comments_text,
            "active": not _yesno(row.get("ObsoleteFlag")),
            "ufs_step1_cust_id": _s(row.get("CustID")) or False,
            "ufs_cust_status": _s(row.get("CustStatus")) or False,
            "ufs_sman_code": _s(row.get("SmanCode")) or False,
            "ufs_sman_name": _s(row.get("SalesmanName")) or False,
            "ufs_branch_code": _s(row.get("BranchCode")) or False,
            "ufs_market_group": _s(row.get("MarketGroup")) or False,
            "ufs_pricing_class": _s(row.get("PricingClassCode")) or False,
            "ufs_sales_class": _s(row.get("SalesClass")) or False,
            "ufs_fob": _s(row.get("FOB")) or False,
            "ufs_frt_ppd_collect": _s(row.get("FrtPpdCollect")) or False,
            "ufs_warehouse_code": _s(row.get("WHCode")) or False,
            "ufs_resale_tax_num": _s(row.get("ResaleTaxNum")) or False,
            "ufs_po_required": _yesno(row.get("PORequiredFlag")),
            "ufs_blanket_po": _s(row.get("BlanketPONum")) or False,
            "ufs_key_customer": _yesno(row.get("KeyCust")),
            "ufs_terms_text": terms_text or False,
            "ufs_carrier": _s(row.get("Carrier")) or False,
        }
        # Office contact name is captured on the ship-to child partner
        # (when present); no direct field for it on the main record.
        _ = contact_name
        if state:
            vals["state_id"] = state.id
        if country:
            vals["country_id"] = country.id
        if payment_term and "property_payment_term_id" in self.env["res.partner"]._fields:
            vals["property_payment_term_id"] = payment_term.id
        # Credit limit lives in the accounting module; only set if present.
        if "credit_limit" in self.env["res.partner"]._fields:
            vals["credit_limit"] = _to_float(row.get("CreditLimit"))
        # Wholesale state: imported customers count as approved (they're
        # established accounts, not applicants).
        if "ufs_wholesale_state" in self.env["res.partner"]._fields:
            vals["ufs_wholesale_state"] = "approved"
        # Default pricing scheme (from ufs_customer_pricing)
        if pricing_scheme and "ufs_default_price_opt" in self.env["res.partner"]._fields:
            vals["ufs_default_price_opt"] = pricing_scheme
        return vals

    @api.model
    def _find_payment_term(self, text):
        if not text:
            return None
        Term = self.env.get("account.payment.term")
        if Term is None:
            return None
        return Term.sudo().with_context(active_test=False).search(
            [("name", "=ilike", text)], limit=1,
        ) or None

    @api.model
    def _has_primary_shipto(self, row):
        return bool(
            _s(row.get("PrimaryShipCustomerName"))
            or _s(row.get("PrimaryShipAddress1"))
            or _s(row.get("PrimaryShipCity"))
        )

    @api.model
    def _upsert_primary_shipto(self, parent, row):
        Partner = self.env["res.partner"].sudo()
        code = _s(row.get("PrimaryShipToCode"))
        name = _s(row.get("PrimaryShipCustomerName")) or parent.name
        state = self._find_state(_s(row.get("PrimaryShipState")))
        country = state.country_id if state else self._find_country("US")
        instructions = "\n".join(filter(None, [
            _s(row.get("PrimaryShipInstructions1")),
            _s(row.get("PrimaryShipInstructions2")),
            _s(row.get("PrimaryShipInstructions3")),
        ])) or False
        vals = {
            "parent_id": parent.id,
            "type": "delivery",
            "name": name,
            "street": _s(row.get("PrimaryShipAddress1")) or False,
            "street2": _s(row.get("PrimaryShipAddress2")) or False,
            "city": _s(row.get("PrimaryShipCity")) or False,
            "zip": _s(row.get("PrimaryShipZip")) or False,
            "ref": ("ST:%s" % code) if code else False,
            "comment": instructions,
        }
        if state:
            vals["state_id"] = state.id
        if country:
            vals["country_id"] = country.id
        domain = [("parent_id", "=", parent.id), ("type", "=", "delivery")]
        if code:
            existing = Partner.search(domain + [("ref", "=", "ST:%s" % code)], limit=1)
        else:
            existing = Partner.search(
                domain + [("street", "=", _s(row.get("PrimaryShipAddress1")))],
                limit=1,
            )
        if existing:
            existing.write(vals)
            return False
        Partner.create(vals)
        return True

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
            vals = self._product_vals(row, has_item_code_field, is_new=is_new)

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
    def _product_vals(self, row, has_item_code_field, is_new=False):
        Template = self.env["product.template"]
        fields_map = Template._fields
        name = _s(row.get("ItemDescription")) or _normalize_item_code(row.get("ItemCode"))
        ext_desc = _s(row.get("ItemExtendedDescription"))
        # Pick a cost — prefer LastUnitCost, fall back to AveUnitCost/StdUnitCost.
        cost = (_to_float(row.get("LastUnitCost"))
                or _to_float(row.get("AveUnitCost"))
                or _to_float(row.get("StdUnitCost")))
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
        # UoM (purchase + stock). Changing uom_id on a product that already
        # has posted journal entries raises a hard error in Odoo, so only
        # set it for brand-new products.
        if is_new:
            uom = self.env["ufsales.product.importer"]._ensure_uom(
                row.get("StockUnit") or row.get("PriceUnit"),
                {"uoms_created": 0},
            )
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

            # Reorder rule. Odoo enforces product_min_qty <= product_max_qty;
            # STEP1 occasionally ships LinePoint < ReorderPoint, so clamp.
            reorder_pt = _to_float(row.get("ReorderPoint"))
            line_pt = _to_float(row.get("LinePoint"))
            reorder_qty = _to_float(row.get("ReorderQty"))
            if (reorder_pt or line_pt or reorder_qty) and template.product_variant_ids:
                max_qty = line_pt or (reorder_pt + reorder_qty) or reorder_pt
                if max_qty < reorder_pt:
                    max_qty = reorder_pt
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
                    "product_max_qty": max_qty,
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

    # ================================================================
    # 5. PO History (inert)
    # ================================================================
    @api.model
    def run_po_history_import(self, summary_source=None, detail_source=None):
        """Import historical purchase orders as inert reference records.

        - Idempotent on `purchase.order.ufs_step1_po_number`.
        - State is written directly (no `button_confirm`), so no pickings,
          stock moves, or vendor bills are generated.
        - Vendors are matched by `ufs_step1_vendor_acct`. POs whose vendor
          can't be resolved are skipped.
        - Lines whose ItemCode doesn't resolve to a product are dropped
          (the header is still imported with the lines that do resolve).
        - Commits every %d POs so very large imports don't blow up the
          transaction.
        """ % _PO_COMMIT_BATCH
        summary_rows = self._read_csv(summary_source, _DEFAULT_PO_SUMMARY_CSV)
        detail_rows = self._read_csv(detail_source, _DEFAULT_PO_DETAIL_CSV)
        if not summary_rows:
            raise UserError(_("PO Summary CSV is empty."))
        if "PONumber" not in summary_rows[0].keys():
            raise UserError(_(
                "This doesn't look like a PO Summary export (no PONumber column)."
            ))
        if detail_rows and "PONumber" not in detail_rows[0].keys():
            raise UserError(_(
                "This doesn't look like a PO Detail export (no PONumber column)."
            ))

        Order = self.env["purchase.order"].sudo()
        OrderLine = self.env["purchase.order.line"].sudo()
        Partner = self.env["res.partner"].sudo()
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()

        # ---- prefetch lookups ----
        vendors_by_acct = {
            p.ufs_step1_vendor_acct: p
            for p in Partner.search([("ufs_step1_vendor_acct", "!=", False)])
        }
        existing_pos = set(
            r["ufs_step1_po_number"] for r in Order.search_read(
                [("ufs_step1_po_number", "!=", False)],
                ["ufs_step1_po_number"],
            )
        )
        # product map by default_code (variant) and template default_code
        products_by_code = {}
        for p in Product.search([("default_code", "!=", False)]):
            products_by_code.setdefault(p.default_code, p)
        # also map item_code stamp if present
        if "ufs_step1_item_code" in Template._fields:
            for t in Template.search([("ufs_step1_item_code", "!=", False)]):
                if t.product_variant_id:
                    products_by_code.setdefault(
                        t.ufs_step1_item_code, t.product_variant_id,
                    )

        # ---- group detail by PONumber ----
        lines_by_po = {}
        for row in detail_rows:
            pono = _s(row.get("PONumber"))
            if not pono:
                continue
            lines_by_po.setdefault(pono, []).append(row)

        created = skipped_existing = skipped_no_vendor = 0
        skipped_no_lines = lines_dropped = 0
        # silence chatter and avoid auto-subscribe overhead during bulk import
        ctx = {
            "tracking_disable": True,
            "mail_create_nolog": True,
            "mail_create_nosubscribe": True,
            "mail_notrack": True,
        }
        Order = Order.with_context(**ctx)
        OrderLine = OrderLine.with_context(**ctx)

        for idx, row in enumerate(summary_rows, start=1):
            pono = _s(row.get("PONumber"))
            if not pono:
                continue
            if pono in existing_pos:
                skipped_existing += 1
                continue
            vendor = vendors_by_acct.get(_s(row.get("VendorAcct")))
            if not vendor:
                skipped_no_vendor += 1
                continue

            line_vals_list = []
            for lrow in lines_by_po.get(pono, []):
                lv = self._po_line_vals(lrow, products_by_code)
                if lv is None:
                    lines_dropped += 1
                    continue
                line_vals_list.append((0, 0, lv))

            if not line_vals_list:
                skipped_no_lines += 1
                continue

            header_vals = self._po_header_vals(row, vendor)
            header_vals["order_line"] = line_vals_list
            header_vals["ufs_step1_po_number"] = pono
            header_vals["ufs_step1_imported"] = True

            order = Order.create(header_vals)
            # Bypass workflow: write state directly so no picking/invoice
            # is generated and no stock moves are created.
            target_state = self._po_target_state(row)
            if target_state and target_state != order.state:
                order.write({"state": target_state})
            created += 1
            existing_pos.add(pono)

            if created % _PO_COMMIT_BATCH == 0:
                self.env.cr.commit()
                _logger.info("UFS PO history: committed %s POs", created)

        _logger.info(
            "UFS PO history: %s created, %s already existed, "
            "%s skipped (vendor missing), %s skipped (no resolvable lines), "
            "%s lines dropped (product missing)",
            created, skipped_existing, skipped_no_vendor,
            skipped_no_lines, lines_dropped,
        )
        return {
            "created": created,
            "skipped_existing": skipped_existing,
            "skipped_no_vendor": skipped_no_vendor,
            "skipped_no_lines": skipped_no_lines,
            "lines_dropped": lines_dropped,
        }

    @api.model
    def _po_header_vals(self, row, vendor):
        po_date = _to_date(row.get("PODate"))
        date_order = datetime.combine(po_date, datetime.min.time()) \
            if po_date else fields.Datetime.now()
        date_received = _to_date(row.get("DateReceived"))
        exp_receive = _to_date(row.get("ExpReceiveDate"))
        notes_bits = []
        for k in (
            "SpecialInstructions1", "SpecialInstructions2",
            "SpecialInstructions3", "MiscChgDesc",
        ):
            v = _s(row.get(k))
            if v:
                notes_bits.append(v)
        vals = {
            "partner_id": vendor.id,
            "partner_ref": _s(row.get("PONumber")) or False,
            "date_order": date_order,
            "ufs_step1_status": _s(row.get("Status")) or False,
            "ufs_step1_wh_code": _s(row.get("WHCode")) or False,
            "ufs_step1_carrier": _s(row.get("Carrier")) or False,
            "ufs_step1_terms": _s(row.get("Terms")) or False,
        }
        if "date_approve" in self.env["purchase.order"]._fields and date_received:
            vals["date_approve"] = datetime.combine(
                date_received, datetime.min.time(),
            )
        if exp_receive and "date_planned" in self.env["purchase.order"]._fields:
            vals["date_planned"] = datetime.combine(
                exp_receive, datetime.min.time(),
            )
        if notes_bits:
            vals["notes"] = " | ".join(notes_bits)
        return vals

    @api.model
    def _po_line_vals(self, row, products_by_code):
        sku = _normalize_item_code(row.get("ItemCode"))
        if not sku:
            return None
        product = products_by_code.get(sku)
        if not product:
            return None
        qty = _to_float(row.get("StockQtyOrdered")) or _to_float(row.get("NumOrdered"))
        if qty <= 0:
            qty = 1.0
        unit_cost = _to_float(row.get("StockUnitCost")) or _to_float(row.get("POCost"))
        desc = _s(row.get("Description")) or product.display_name
        date_planned = _to_date(row.get("ExpReceiveDate")) \
            or _to_date(row.get("BOExpReceiveDate"))
        vals = {
            "product_id": product.id,
            "name": desc,
            "product_qty": qty,
            "price_unit": unit_cost,
            "product_uom": product.uom_po_id.id or product.uom_id.id,
            "ufs_step1_line_num": _to_int(row.get("LineNum")),
            "ufs_step1_qty_received": _to_float(row.get("StockQtyReceived"))
                or _to_float(row.get("NumReceived")),
            "ufs_step1_qty_backorder": _to_float(row.get("StockQtyBO"))
                or _to_float(row.get("NumBO")),
        }
        if date_planned:
            vals["date_planned"] = datetime.combine(
                date_planned, datetime.min.time(),
            )
        return vals

    @api.model
    def _po_target_state(self, row):
        """Map STEP1 status to an Odoo purchase.order state. We bypass the
        workflow by writing state directly, so this purely affects how the
        record is displayed and filtered."""
        code = _s(row.get("StatusCode")).upper()
        status = _s(row.get("Status")).upper()
        if code == "R" or status == "RECEIVED":
            return "purchase"
        if code == "I" or _yesno(row.get("POIssuedFlag")):
            return "purchase"
        if code == "B" or status == "BACKORDER":
            return "purchase"
        if status in ("CANCELLED", "CANCELED", "VOID", "VOIDED"):
            return "cancel"
        # Default: leave as draft for anything that wasn't issued.
        return "draft"

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
