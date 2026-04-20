# UF Sales Product Import (`ufsales_product_import`)

Two-stage importer for the UF Sales catalog on Odoo 19:

- **Stage 1 — JSON catalog** (auto, on install): imports the
  website-scraped catalog from `data/ufsales_products.json` into
  `product.category`, `product.public.category`, `product.template`,
  and `product.image`. Products are created **published** with real
  images.
- **Stage 2 — STEP1 CSV backfill** (manual, via wizard): imports
  vendors, per-product inventory info, warehouse stock, reorder
  rules, and quantity-bracket pricing from STEP1 exports. Products
  new to Odoo come in **unpublished with the UFS placeholder image**;
  existing products are updated in place and their publish state /
  images are preserved.

Depends on: `product`, `website_sale`, `stock`, `purchase`,
`ufs_customer_pricing`.

---

## Install / upgrade

1. Drop `ufsales_product_import/` into the Odoo addons path.
2. **Apps → Update Apps List** → install **UF Sales Product Import**.
3. The JSON importer fires from `post_init_hook`. On re-install or
   `-u`, migrations under `migrations/<version>/` re-run the importer
   so changes (tax clearing, image fallback, catalog updates) apply.

---

## Stage 1 — JSON catalog

### Source file

Bundled at `ufsales_product_import/data/ufsales_products.json`.
Alternate lookup order:

1. `ir.config_parameter` `ufsales_product_import.json_path`
2. `data/ufsales_products.json` inside the module
3. `ufsales_products.json` next to the custom addons directory
4. `/Applications/MAMP/htdocs/UFS/UFS/ufsales/ufsales_products.json`

### What it imports

- Builds the `category_path` hierarchy on both `product.category` and
  `product.public.category`.
- Upserts products by SKU (`item_number` → `default_code`).
- Maps `name`, `price`, descriptions, UoM, and source metadata.
- Downloads primary and secondary images when the server can reach
  the source URLs; falls back to `data/ufs.png` if not.
- Clears tax assignments on every product at the end (UFS handles
  tax downstream).

### Rerun

Idempotent. From an Odoo shell:

```python
env["ufsales.product.importer"].run_import()
```

---

## Stage 2 — STEP1 CSV backfill

### What it does

| CSV                          | Target                                           |
|------------------------------|--------------------------------------------------|
| `vendors.csv`                | `res.partner` (supplier_rank=1)                  |
| `product_inventory_info.csv` | `product.template` + `product.supplierinfo` + quantity-tier pricelist |
| `warehouse.csv`              | `stock.quant` + `stock.warehouse.orderpoint` + bin # on template |

Run order is enforced by the wizard: **Vendors → Products → Warehouse**.
Vendors must exist before products so supplierinfo rows can link;
products must exist before warehouse so stock/orderpoints target real
SKUs.

### How to run

**Menu:** *Inventory → UF Sales Import → Import from STEP1*
**Role:** Inventory / Administrator (`stock.group_stock_manager`).

The wizard lets you:

- Tick which stages to run (default: all three).
- Optionally upload your own CSV for any stage. If left empty, the
  importer uses the CSV bundled at `ufsales_product_import/data/`.

Click **Run Import**. The wizard prints a per-stage count
(`created=… updated=… skipped=…`) on completion. Errors from a stage
do not abort the others.

Reruns are safe — every stage is idempotent (upsert by legacy key).

### Bundled CSVs

Live in `ufsales_product_import/data/`:

- `vendors.csv`
- `product_inventory_info.csv`
- `warehouse.csv`

Replace them in-repo to update the default import, or just upload
fresh ones via the wizard.

---

## Vendor import (`vendors.csv`)

**Key:** `VendorAcct` → `res.partner.ufs_step1_vendor_acct`.

| CSV column                         | Odoo target                      |
|------------------------------------|----------------------------------|
| `VendorAcct`                       | `ufs_step1_vendor_acct`, `ref`   |
| `VendorID`                         | `ufs_step1_vendor_id`            |
| `VendorName`                       | `name`                           |
| `VendorGroupCode`                  | `ufs_vendor_group_code`          |
| `Address1` / `Address2`            | `street` / `street2`             |
| `City`, `State`, `Zip`             | `city`, `state_id`, `zip` (state resolved by code then name against US) |
| `OfficePhone`                      | `phone`                          |
| `OfficeContactEmailAddress` / `POContactEmailAddress` | `email` (first non-empty) |
| `WebAddress`                       | `website`                        |
| `Carrier`                          | `ufs_carrier`                    |
| `ObsoleteFlag`                     | `active` (inverse)               |

Partner defaults: `company_type='company'`, `supplier_rank=1`,
`customer_rank=0`.

---

## Product import (`product_inventory_info.csv`)

**Key:** `ItemCode` → `product.template.ufs_step1_item_code` (from
`ufs_customer_pricing`), falling back to `default_code`. Leading `[`
in legacy ItemCode exports is stripped.

### New product defaults (not updated on existing products)

- `default_code = ItemCode`
- `ufs_step1_item_code = ItemCode`
- `is_published = False` / `website_published = False`
- `image_1920 = data/ufs.png` (bundled placeholder)
- `type = 'consu'`, `is_storable = True`

### Fields written on every upsert

| CSV column                                           | Odoo target                     |
|------------------------------------------------------|---------------------------------|
| `ItemDescription`                                    | `name`                          |
| `ItemExtendedDescription`                            | `description_sale`              |
| `ListPrice`                                          | `list_price`                    |
| `LastUnitCost` / `AveUnitCost` / `StdUnitCost`       | `standard_price` (first non-zero) |
| `UPCCode` / `SupplierUPCCode`                        | `barcode` (first non-empty)     |
| `StockUnit` / `PriceUnit`                            | `uom_id`, `uom_po_id` (via UoM resolver) |
| `StockUnitShipWgt`                                   | `weight`                        |
| `StockUnitShipCubes`                                 | `volume`                        |
| `StockClass`                                         | `ufs_stock_class`               |
| `SalesClass`                                         | `ufs_sales_class_code`          |
| `MSDSCode`                                           | `ufs_msds_code`                 |
| `HazMatCode` / `HazMatFlag`                          | `ufs_hazmat_code`, `ufs_hazmat` |
| `ObsoleteFlag`                                       | `ufs_is_obsolete`, `active` inv |
| `ItemID`                                             | `ufs_step1_item_id`             |

### Supplier info

For each product, up to two `product.supplierinfo` rows are written
from:

- Primary — `SupplierAcct` / `SupplierPartNum`
- Alternate — `AltSupplierAcct` / `AltSupplierPartNum`

Vendors are resolved by `ufs_step1_vendor_acct`. Rows for a vendor
not found in Odoo are simply skipped. Price defaults to `LastPOCost`
or `LastUnitCost`. Existing imported supplierinfo for this product
not represented in the current row is removed; manually added
supplierinfo (partner without `ufs_step1_vendor_acct`) is left alone.

### Quantity-tier pricelist

The importer maintains a shared pricelist named
**UFS Quantity Brackets** (auto-created if missing). For each product
that has any `Price2…Price8` with a matching `MinQty2…MinQty8`, a
`product.pricelist.item` is created with:

- `applied_on = 0_product_variant` (when the template has a single
  variant; otherwise `1_product`).
- `compute_price = fixed`
- `min_quantity = MinQtyN`
- `fixed_price = PriceN`

Tiers with `price <= 0` or `min_qty <= 1` are skipped (the base
price is already on `list_price`). Re-running the importer **wipes
and rewrites** items for each touched product, so stale tiers are
cleaned up.

Apply the pricelist per customer (*Partner → Sales & Purchase → Sales
Pricelist*) or set it on a website for the public storefront.

---

## Warehouse / inventory import (`warehouse.csv`)

**Key:** `ItemCode` → existing product.
**Warehouse key:** `WHCode` (stripped of leading `*`).

For the single `*MAIN` warehouse the importer **reuses the Odoo
default warehouse** rather than creating a duplicate, and stamps it
with `ufs_step1_wh_code='MAIN'`.

### What gets updated per row

| CSV column        | Odoo target                                         |
|-------------------|-----------------------------------------------------|
| `BinNumber`       | `product.template.ufs_bin_number` (only set if empty) |
| `StockOnHand`     | `stock.quant.inventory_quantity` at the warehouse's stock location (applied as an inventory adjustment) |
| `ReorderPoint`    | `stock.warehouse.orderpoint.product_min_qty`        |
| `LinePoint`       | `stock.warehouse.orderpoint.product_max_qty`        |
| `ReorderQty`      | `stock.warehouse.orderpoint.qty_to_order_manual`, plus `product_max_qty = ReorderPoint + ReorderQty` when `LinePoint` is blank |

Rows whose product is not in Odoo are counted as skipped.

Bin numbers assume one warehouse per product. If you later operate
multiple physical locations, migrate bins onto `stock.location`
records and drop `ufs_bin_number`.

---

## Fields added by this module

### `res.partner`

- `ufs_step1_vendor_acct` *(indexed)*
- `ufs_step1_vendor_id`
- `ufs_vendor_group_code`
- `ufs_carrier`

### `product.template`

- `ufs_step1_item_id` *(indexed)*
- `ufs_bin_number`
- `ufs_stock_class`, `ufs_sales_class_code` *(indexed)*
- `ufs_price_unit`, `ufs_stock_unit`, `ufs_purch_unit`
- `ufs_msds_code`, `ufs_hazmat_code`, `ufs_hazmat`
- `ufs_is_obsolete`

`ufs_step1_item_code` and `ufs_sales_class` come from the
`ufs_customer_pricing` dependency.

### `stock.warehouse`

- `ufs_step1_wh_code` *(indexed)*

---

## Troubleshooting

**"Vendors" step shows many skips.**
Either `VendorAcct` or `VendorName` was empty on those rows. Fix the
source CSV or ignore — partners without names cannot be created.

**Supplier info not linking on product import.**
Run **Vendors** first (same wizard). A missing vendor yields a silent
skip for supplierinfo; the product still imports.

**Stock adjustment fails on a product.**
Ensure the product has `is_storable=True`. Service or non-stockable
types cannot hold quants. The importer sets `is_storable=True` on
new products; for existing products you may need to flip the type
first.

**Barcode uniqueness error.**
Two products share the same `UPCCode`. Fix in the source CSV — Odoo
enforces barcode uniqueness on `product.template` / `product.product`.

**"Bundled CSV not found."**
Either the module wasn't installed with the `data/` directory present,
or the wrong filename. Upload the CSV via the wizard to override.

**Wrong currency on the quantity-bracket pricelist.**
The pricelist is created with `self.env.company.currency_id`. If you
run the import under a different company context you'll get a
mismatched pricelist — delete it and re-run under the right company.

---

## Programmatic API

From an Odoo shell:

```python
imp = env["ufsales.step1.csv.importer"]
imp.run_vendor_import()        # bundled CSV
imp.run_product_import()       # bundled CSV
imp.run_warehouse_import()     # bundled CSV

# Override with your own base64 payload:
imp.run_vendor_import(my_base64_bytes)
```

All three methods return a dict of counts.

## License

LGPL-3.
