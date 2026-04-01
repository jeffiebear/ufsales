# UF Sales Product Import (`ufsales_product_import`)

One-time Odoo 19 addon that imports the catalog in `ufsales_products.json` into:

- `product.category`
- `product.public.category`
- `product.template`
- `product.image`

This addon is set up to work on `odoo.sh`, where the JSON must be shipped inside the module instead of referenced from a local workstation path.

## What it does

- Builds the same category hierarchy from each `category_path`
- Assigns the deepest internal category to `categ_id`
- Assigns the full website category path to `public_categ_ids`
- Upserts products by SKU (`item_number` -> `default_code`)
- Maps source price, descriptions, UoM, image URLs, and source metadata
- Downloads product images when the Odoo server can reach the source URLs

## Install

1. Add this repo to the Odoo addons path.
2. Update the Apps list.
3. Install **UF Sales Product Import**.

The import runs automatically from the module `post_init_hook`.

## Source file path

For `odoo.sh`, the source file is now bundled in the addon at:

- `ufsales_product_import/data/ufsales_products.json`

The importer also looks for:

- `ufsales_products.json` next to the custom addons
- `/Applications/MAMP/htdocs/UFS/UFS/ufsales/ufsales_products.json`

You can override that path with the system parameter:

- `ufsales_product_import.json_path`

## Rerun

The import is idempotent. It can be rerun from an Odoo shell:

```python
env["ufsales.product.importer"].run_import()
```
