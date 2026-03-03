# UF Sales Catalog Seed (`ufsales_catalog_seed`)

This addon seeds a baseline Website + eCommerce catalog for Odoo 19.

## What it creates

- Website public categories (`product.public.category`) with a 3-level hierarchy
- Product attributes and values for website filters/variants:
  - `Size`: S, M, L, XL
  - `Pack`: Single, Case of 25
- Demo products (`product.template`) with:
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

## Demo data

`demo/demo_products.xml` is loaded only when demo data is enabled for the database.

- Odoo.sh: enable demo data when creating/restoring the database used for testing.
- Local Odoo: start/create DB with demo data enabled (for example `--without-demo=0`).

If demo data is disabled, categories/attributes still load from `/data`.

## Images

The module includes image files under:

- `static/src/img/categories/`
- `static/src/img/products/`

To refresh them from source links, run:

```bash
./tools/download_images.sh
```
