# UF Sales Catalog Seed (`ufsales_catalog_seed`)

This addon seeds a baseline Website + eCommerce catalog for Odoo 19.

## What it creates

- Website public categories (`product.public.category`) with a 3-level hierarchy
- Product attributes and values for website filters/variants:
  - `Size`: S, M, L, XL
  - `Pack`: Single, Case of 25
- Sample products (`product.template`) with:
  - SKU (`default_code`)
  - `list_price`
  - royalty-free demo image (`image_1920` from module files)
  - category assignment (`public_categ_ids`)
  - website publication (`website_published`)
  - variant attribute lines on selected products (Nitrile Gloves, Shipping Box)

## Not included

- Website menu seed records are intentionally **not** loaded.

## Install

1. Add this module to your Odoo addons path.
2. In Apps, run **Update Apps List**.
3. Install **UF Sales Catalog Seed**.

## Sample products loading

Sample products are created by module data actions during install/upgrade, so they are present in any database (even when Odoo demo mode is disabled).

## Images

The module includes image files under:

- `static/src/img/categories/`
- `static/src/img/products/`

To refresh them from source links, run:

```bash
./tools/download_images.sh
```
