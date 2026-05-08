# UFS Customizations

A catch-all module for small, focused tweaks to standard Odoo behavior
that don't justify a module of their own. Each tweak is implemented in
its own file and documented inline so future maintainers can see the
*why* behind it.

## Current tweaks

### Sale order line — margin guide

Adds three columns to the order-line list inside the sale order form:

- **Cost** — `product.standard_price`, converted into the order's
  currency at the order date.
- **Margin** — `price_subtotal − (cost × qty)`.
- **Margin %** — margin / subtotal × 100.

These are a live decision aid for staff entering manual quotes/orders
— they update as the line is edited and are not stored on the record.
The fields and their view columns are gated behind
`sales_team.group_sale_salesman`, so portal users and the public
website templates never see them.

If we later need stored margin for reporting, switch the fields to
`store=True` or layer in Odoo's official `sale_margin` module on top.

### Sale order — Create Customer Price Rules button

A header button on the sale order form (internal sales users only)
that snapshots each line's unit price into a Special Price rule on
`ufs_customer_pricing`. Conflict policy is **skip, don't overwrite**:
if the customer already has *any* rule for that product (active or
not, any rule_type), the line is left alone. The toast at the end
reports created vs. skipped counts.

Creating the first rule for a customer provisions their UFS pricelist
and writes it to `partner.property_product_pricelist` — the standard
Odoo hook that auto-loads the pricelist on subsequent quotes. The
button also refreshes the *current* order's `pricelist_id` so any
further lines added to this same quote pick up the rules natively.

To override an existing rule, edit it directly under
**Sales → Customer Price Rules** instead of using the button.

## Adding a new tweak

1. Drop a new file under `models/` (e.g. `account_move.py`) and
   register it in `models/__init__.py`.
2. If it needs view changes, add a file under `views/` and list it in
   `__manifest__.py`'s `data` array.
3. Lead the file with a docstring explaining what the tweak does and
   *why it exists* — the next person reading it will thank you.

## Install / upgrade

```bash
# from the Odoo CLI
odoo -u ufs_customizations
```
