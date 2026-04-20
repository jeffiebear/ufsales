# UFS Customer Pricing (`ufs_customer_pricing`)

Per-customer pricing rules for Odoo 19, built to replace STEP1's
`CustomerPriceRule`. Rules are stored in a dedicated model
(`ufs.price.rule`) and auto-synced to one `product.pricelist` per
customer, so standard Odoo quotes, sales orders, and POS pick up the
right price natively — no overrides at the sale-line level.

---

## Contents

- [Install and upgrade](#install-and-upgrade)
- [Concepts](#concepts)
- [Rule types](#rule-types)
- [Administration surfaces](#administration-surfaces)
- [Bulk import from STEP1](#bulk-import-from-step1)
- [Day-to-day administration](#day-to-day-administration)
- [Behavior and guarantees](#behavior-and-guarantees)
- [Permissions](#permissions)
- [Troubleshooting](#troubleshooting)

---

## Install and upgrade

1. Copy `ufs_customer_pricing/` into your Odoo addons path.
2. **Apps → Update Apps List**, then install **UFS Customer Pricing**.
3. Confirm the **Sales → Customer Pricing** menu appears.

To upgrade after a code change:

```bash
odoo-bin -u ufs_customer_pricing -d <database>
```

or via the UI: **Apps → UFS Customer Pricing → Upgrade**.

---

## Concepts

- **Price rule** (`ufs.price.rule`) — one row per `(customer, product)`
  pair. Stores the rule type, its magnitude (percent / special price /
  bracket), sales history carried from STEP1, notes, and flags
  (taxable, commissionable, print-on-order, etc.).
- **Customer pricelist** — each customer gets a single auto-managed
  `product.pricelist` named `Customer Pricelist — <customer>`. The
  module writes `product.pricelist.item` rows to mirror the rules. The
  pricelist is set as the customer's default sales pricelist so it
  applies automatically to new quotes and orders.
- **Customer default scheme** (`Default Pricing Scheme` on the
  customer) — a fallback pricing expression (e.g. `P30`, `M40`, `i`)
  used by any rule whose type is *Use Customer Default*. Changing this
  value re-syncs all default-typed rules for that customer.
- **Live cost pricing** — margin and markup rules are compiled into
  formula pricelist items on `standard_price`. Changing a product's
  cost automatically re-prices every margin/markup rule that uses it,
  on the next quote.

---

## Rule types

| STEP1 code  | Rule Type              | How Odoo prices it                                        |
|-------------|------------------------|-----------------------------------------------------------|
| `S`         | Special Price (fixed)  | Fixed price — `compute_price=fixed`, `fixed_price=value`. |
| `P{n}`      | Profit Margin %        | `price = cost / (1 - n/100)` — formula on `standard_price`. |
| `M{n}`      | Cost Markup %          | `price = cost · (1 + n/100)` — formula on `standard_price`. |
| `B{n}`      | Quantity Bracket       | Stored; multi-tier sync deferred to v1.1.                 |
| `i` / blank | List Price             | No pricelist item — falls through to `product.list_price`.|
| *(default)* | Use Customer Default   | Resolved at sync time via the customer's default scheme.  |

Lowercase STEP1 codes (`p30`, `m40`, …) are normalized to uppercase on
import. Anything unrecognised resolves to *Use Customer Default*.

---

## Administration surfaces

Rules can be created and edited from three places. They all read and
write the same `ufs.price.rule` records.

### 1. Customer form — **UFS Pricing** tab

*Contacts / Customers → open a customer → UFS Pricing*

- **STEP1 CustAcct** — legacy lookup key (used by import).
- **Default Pricing Scheme** — the fallback expression, e.g. `P30`.
  Changing this re-syncs every default-typed rule for the customer.
- **UFS Customer Pricelist** — read-only pointer to the auto-managed
  pricelist.
- **Price Rules** grid — editable inline. Add, edit, archive rules for
  this customer.
- **Price Rules** smart button — drills into a filtered list view
  scoped to the customer.

### 2. Product form — **Customer Pricing** tab

*Inventory or Sales → Products → open a product → Customer Pricing*

- **STEP1 Item Code** — legacy lookup key (used by import).
- **Per-Customer Rules** — every rule touching this product, across
  all customers. Click a row to edit, or **Add a line** to create a
  new rule for this product (the product is pre-filled when the
  template has a single variant).
- **Customer Rules** smart button — drills into a filtered list view
  scoped to the product.

### 3. Dedicated menu — **Sales → Customer Pricing → Customer Price Rules**

The canonical list / form / search view.

- Search by customer, product, customer part #, or sales class.
- Built-in filters: *Special / Margin / Markup / List / Default*,
  *Imported from STEP1*, *Archived*.
- Group by: Customer, Product, Rule Type, Sales Class.
- The form view shows the full STEP1 payload (sales history, notes,
  flags) plus a **Re-sync to Pricelist** button that forces a rebuild
  of the linked pricelist item.

---

## Bulk import from STEP1

A CSV importer is shipped with the module.

**Menu:** *Sales → Customer Pricing → Import from STEP1*
**Required role:** Sales Manager.

### Before you import

The importer looks customers and products up by legacy STEP1 keys, so
those must be in Odoo first:

1. **Customers** — each `res.partner` that should receive rules must
   have `ufs_step1_cust_acct` populated. Use Odoo's standard CSV
   importer on `res.partner`, mapping:
   - `CustAcct` → `STEP1 CustAcct`
   - `DefaultPriceOpt` → `Default Pricing Scheme`
2. **Products** — each `product.template` that should receive rules
   must have `ufs_step1_item_code` populated. Map:
   - `ItemCode` → `STEP1 Item Code`

Rows whose customer or product cannot be resolved are **skipped** and
counted in the import log — unless you tick *Create Missing Customers*
/ *Create Missing Products*, which creates stubs.

### Running the import

The cleaned STEP1 export is bundled at:

```
ufs_customer_pricing/data/UFS_CustomerPriceRules_cleaned.csv
```

1. Open **Sales → Customer Pricing → Import from STEP1**.
2. **STEP1 Export CSV** — attach the file above (or a newer export).
3. Options:
   - **Create Missing Customers** — auto-create stub partners for
     `CustAcct` values not found.
   - **Create Missing Products** — auto-create stub products for
     `ItemCode` values not found.
   - **Replace Existing Imported Rules** — delete every rule that was
     previously imported from STEP1 (`step1_imported = True`) before
     running. Use this for a clean re-import.
4. Click **Import**.

The importer upserts on `(customer, product)` — running it twice
against the same file produces no duplicates.

### What the importer reads

| CSV column         | Used as                                            |
|--------------------|----------------------------------------------------|
| `CustAcct`         | Customer lookup. Strips a leading `*` on fallback. |
| `ItemCode`         | Product lookup by `STEP1 Item Code`.               |
| `CPPriceOpt`       | **Authoritative** rule type: `S` / `P` / `M` / `B`.|
| `CPPricePct`       | Percentage value for `P` and `M`.                  |
| `CPPriceBrkt`      | Bracket number for `B`.                            |
| `CPSpecialPrice`   | Fixed price for `S`.                               |
| `PriceOpt`         | Fallback type code when `CPPriceOpt` is blank.     |
| `ListPrice`, `CurrentPrice`, `LastPricePaid`, `LastQtyOrdered` | Sales history snapshot fields. |
| `FirstSaleDate`, `LastSaleDate`, `NextSaleDate` | Sales history dates.          |
| `CPNotes1–3`, `CPNotesDate`, `CPNotesAddToOrder`, `CPPrintOnOrderForm` | Notes. |
| `CustomerPartNum`, `SalesClass`, `CPTaxFlag`, `CPComFlag`         | Reference. |

### Reading the import log

After a run the wizard shows counts for *Created*, *Updated*, *Skipped
(customer not found)*, *Skipped (product not found)*, *Errors*, plus
the first 50 error rows with their line numbers.

---

## Day-to-day administration

### Add a rule for one customer + product

Any of the three surfaces works. Fastest path: open the customer form,
go to **UFS Pricing**, click **Add a line**, pick a product, pick a
**Rule Type**, fill in the required value (price / margin % / markup
%), save.

### Change a customer's default scheme

Open the customer form → **UFS Pricing** → edit **Default Pricing
Scheme** (examples: `i`, `P30`, `M40`). Save.

Every rule owned by this customer whose type is *Use Customer Default*
is automatically re-synced — their linked pricelist items are
rewritten to match the new scheme.

### Archive (soft-delete) a rule

Toggle the **Active** switch off on the rule. The linked pricelist
item is removed immediately, so the customer falls back to their
default (or list price). Flip it back on to restore.

### Hard-delete a rule

Only *Sales Managers* can delete. Deleting a rule removes its linked
pricelist item as well.

### Manually re-sync a rule

Open the rule form and click **Re-sync to Pricelist** in the header.
Use this after fixing bad data or if something was edited on the
pricelist directly and needs to be rebuilt.

### Time-boxed rules

Set **Start Date** / **End Date** on the rule. Values propagate to the
pricelist item's `date_start` / `date_end` — Odoo's pricelist engine
picks rules automatically based on the quote date.

---

## Behavior and guarantees

- **Cost-driven rules recompute live.** Margin and markup rules are
  written as formula pricelist items on `standard_price`. Every time
  you change a product's cost, the next quote reflects the new price
  — no manual re-sync needed. If you want a price frozen at today's
  cost, switch the rule to *Special Price* and copy the value.
- **The per-customer pricelist is auto-managed.** Do not hand-edit
  `Customer Pricelist — <customer>` or its items — they will be
  overwritten on the next rule change. Manage everything through
  `ufs.price.rule`.
- **Re-imports are idempotent.** The wizard upserts by
  `(customer, product)`. Use *Replace Existing Imported Rules* to
  start from scratch.
- **Default-scheme propagation.** Changing a customer's
  `Default Pricing Scheme` automatically re-syncs every rule of type
  *Use Customer Default* for that customer.
- **Archiving is reversible.** Toggling `active` off removes the
  pricelist item but preserves the rule's configuration and history.
- **Multi-company.** Rules are scoped to a company; an `ir.rule`
  enforces that users only see rules for their allowed companies.

---

## Permissions

| Group                           | Read | Write | Create | Delete |
|---------------------------------|:----:|:-----:|:------:|:------:|
| Sales / User (`group_sale_salesman`)  | ✔ | ✔ | ✔ | ✘ |
| Sales / Administrator (`group_sale_manager`) | ✔ | ✔ | ✔ | ✔ |

Only *Sales Administrator* sees the **Import from STEP1** menu.

---

## Troubleshooting

**"Skipped (customer not found)" for rows I expected to match.**
The CSV key is `CustAcct`; Odoo expects the exact value in
`STEP1 CustAcct` on the partner. STEP1 prefixes some accounts with
`*` — the importer first tries the raw value, then retries without the
leading `*`. If rows are still skipped, import or fix the customer
first.

**"Skipped (product not found)".**
Ensure the product template has `STEP1 Item Code` set to the exact
`ItemCode` value from the CSV.

**A customer's quote is not picking up the rule.**
- Confirm the customer has a **UFS Customer Pricelist** on the
  *UFS Pricing* tab. Open the rule and click **Re-sync to Pricelist**
  if the linked item is missing.
- Confirm the partner's **Sales Pricelist** (on the Sales & Purchase
  tab) is the customer pricelist. The module sets it on first sync;
  if it was cleared, re-sync any rule to restore it.
- Confirm the rule is **Active** and the quote's date falls between
  any configured **Start Date** / **End Date**.

**Margin-rule save fails with "Profit margin must be less than 100%".**
A 100 % margin is mathematically undefined (division by zero). Use
99.99 % or switch to a *Special Price* / *Cost Markup* rule.

**Changed `standard_price` but the price didn't update.**
Margin/markup rules read `standard_price` at quote time — if the
quote was created before the cost change, it holds the old price.
Open the quote and re-trigger pricing (change the quantity / pricelist
and revert), or create a new quote.

---

## Roadmap

- v1.1 — Quantity bracket sync (multi-tier pricelist items with
  `min_quantity`).
- v1.1 — Bulk update wizard (e.g. "raise every `P30` rule for sales
  class `X` to `P32`").
- v1.2 — Render `CPNotes` + `CPNotesAddToOrder` on sale order form /
  printout.

## License

LGPL-3.
