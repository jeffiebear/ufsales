# UFS Wholesale Access (`ufs_wholesale`)

Gates the Odoo 19 website storefront (`website_sale`) behind a
wholesale-only approval workflow. Visitors cannot see prices, add
items to a cart, or reach checkout until an administrator approves
their application.

---

## Contents

- [What it does](#what-it-does)
- [Install](#install)
- [Data captured on signup](#data-captured-on-signup)
- [Application statuses](#application-statuses)
- [Visitor experience](#visitor-experience)
- [Administering applications](#administering-applications)
- [Emails sent](#emails-sent)
- [Access-control points](#access-control-points)
- [Troubleshooting](#troubleshooting)

---

## What it does

- Extends the standard `/web/signup` form with wholesale-specific
  fields (company, address, FEIN / Tax ID, resale certificate upload).
- Marks every new portal user as **Pending Approval** and emails them
  an acknowledgement.
- Provides an **Approve / Reject** workflow on the user form.
- Sends an approval email with a link to sign in.
- Hides prices, add-to-cart buttons, the cart icon, and the
  "Request a Quote" CTA from anyone not in *Approved* state.
- Blocks the cart / checkout / payment / express-checkout HTTP
  endpoints at the controller level — the UI hiding is reinforced
  server-side so URL-guessing does not bypass it.
- Replaces hidden price/buttons with a **Request Wholesale Access**
  link to the signup page, and shows a notice on product pages
  explaining why pricing is hidden.

---

## Install

1. Copy `ufs_wholesale/` into the Odoo addons path.
2. **Apps → Update Apps List**, then install
   **UFS Wholesale Access**.
3. In *Website → Configuration → Settings*, make sure
   **Free sign up** is enabled (`auth_signup` must allow public
   registration; the signup page is otherwise returned as 404).

To upgrade after a code change:

```bash
odoo-bin -u ufs_wholesale -d <database>
```

Dependencies: `website_sale`, `auth_signup`, `mail`.

---

## Data captured on signup

The signup form at `/web/signup` is extended with:

| Field               | Required | Stored on `res.partner`                    |
|---------------------|:--------:|--------------------------------------------|
| Company Name        | ✔        | `ufs_company_name`, also `company_name` if present |
| Street Address      | ✔        | `street`                                   |
| Address Line 2      |          | `street2`                                  |
| City                | ✔        | `city`                                     |
| State / Region      | ✔        | `ufs_state_text` (free-text mirror)        |
| ZIP / Postal Code   | ✔        | `zip`                                      |
| Country             | ✔        | `ufs_country_text` (free-text mirror)      |
| Phone               |          | `phone`                                    |
| FEIN / Tax ID       | ✔        | `ufs_fein_taxid`, also `vat`               |
| Tax Resale Certificate | ✔     | `ufs_resale_certificate` (base64 attachment), `ufs_resale_certificate_filename` |

Certificate upload constraints:

- Allowed types: **PDF, PNG, JPG, JPEG, WEBP**.
- Maximum size: **10 MB**.
- Empty or missing files are rejected with a form error.

State and Country are captured as free text (not the standard
`state_id` / `country_id`), so applicants can type locations that
don't yet exist as Odoo records. You can clean these up later from
the partner form.

---

## Application statuses

Stored on `res.partner.ufs_wholesale_state`:

| Status        | Set by                         | What it means                                  |
|---------------|--------------------------------|------------------------------------------------|
| **pending**   | Auto — on signup               | Awaiting review. Cannot shop.                  |
| **approved**  | Admin — *Approve Wholesale*    | Can browse prices, add to cart, checkout.      |
| **rejected**  | Admin — *Reject Wholesale*     | Treated the same as *pending* for shopping.    |

> **Note.** The default value on `res.partner` is `approved` so that
> pre-existing partners (imported customers, staff) are not
> accidentally locked out. Only the signup controller forces new
> portal users into `pending`.

Internal users (`share = False`) are always allowed through — the
gate applies only to portal / public accounts.

---

## Visitor experience

### Public (not logged in)

- Can browse `/shop` and product pages.
- Prices are **hidden**.
- Add-to-cart and CTA buttons are **hidden**.
- Cart icon is **hidden** from the header.
- A product-page banner reads:
  *"Pricing and checkout are available only to approved wholesale
  accounts."*
- A **Request Wholesale Access** button links to `/web/signup`.

### Logged in, pending or rejected

Same as public — prices and cart remain hidden. Any attempt to hit
`/shop/cart`, `/shop/cart/add`, `/shop/cart/update`, `/shop/cart/clear`,
`/shop/cart/quick_add`, `/shop/update_address`, or
`/shop/payment/transaction/...` is blocked:

- GET/HTTP routes redirect back to `/shop`.
- JSON-RPC routes raise a `UserError` / return an empty cart payload.

### Logged in and approved

Full storefront behavior — identical to stock `website_sale`.

### After signup

After a successful POST to `/web/signup` the visitor is logged out
(dropped back to the public user) and shown the **Registration
Received** page, then redirected to `/web/login` via its CTA. They
cannot log in until an admin approves them.

---

## Administering applications

### Find the queue

**Website → Configuration → Wholesale → Applications**
*(visible to Administration / Settings users — `base.group_system`)*

The default filter is **Pending**. Use the pills to switch to
**Approved** or **Rejected**.

The list shows:

- Name & Login (email)
- Company Name
- FEIN / Tax ID
- Status
- Signup date

### Review an application

Open the user to see the **Wholesale** tab on the user form:

- Wholesale Status
- *Can Buy on Website* (computed from status + internal flag)
- Company Name, FEIN / Tax ID, State, Country
- Approved By / Approved On (audit fields)
- **Tax Resale Certificate** — click the filename to download the
  uploaded file.

Header buttons:

- **Approve Wholesale** — flips status to *approved*, stamps
  `Approved By` and `Approved On`, and sends the welcome email
  (only the first time — re-approving an already-approved user
  does not re-send).
- **Reject Wholesale** — flips status to *rejected*. No email is
  sent automatically; contact the applicant manually if needed.

Both buttons are no-ops on internal users.

### Re-open an application

Change **Wholesale Status** back to *pending* on the Wholesale tab
(or programmatically via
`res.users.action_ufs_set_wholesale_pending()`), then re-approve.

### Impersonation / manual signup from the backend

If you create a portal user directly in **Settings → Users & Companies
→ Users**, they will default to *approved* (because `res.partner`
defaults to `approved`). Set *Wholesale Status* to *pending* on the
Wholesale tab if you want them to go through review.

---

## Emails sent

Two `mail.template` records, both keyed to `res.users`:

| XML ID                                          | Subject                                 | Sent when                 |
|-------------------------------------------------|-----------------------------------------|---------------------------|
| `ufs_wholesale.mail_template_wholesale_signup_ack` | *We received your UFS Wholesale application* | Immediately after signup. |
| `ufs_wholesale.mail_template_wholesale_welcome`    | *Welcome to UFS Wholesale*                    | On the first *approve* per user. |

Customize them under **Settings → Technical → Email → Templates**
(search for "UFS Wholesale"). The `From` address falls back to the
company formatted email, then the current user's email, then
`noreply@example.com`.

---

## Access-control points

The module enforces the wholesale gate in both the view layer and
the controller layer so the two cannot drift out of sync.

**View layer — hidden when `website._ufs_wholesale_can_buy()` is False:**

- `website_sale.header_cart_link` — header cart icon
- `website_sale.products_item` — product-tile price + add-to-cart;
  replaced with a *Request Wholesale Access* CTA
- `website_sale.product_price` — product-page price
- `website_sale.cta_wrapper` — product-page CTA wrapper
- `website_sale.product` — product-page "not available" banner

**Controller layer — blocked / redirected:**

| Route                                | Type     | Action on block                 |
|--------------------------------------|----------|---------------------------------|
| `GET /shop/cart`                     | http     | Redirect to `/shop` (or `/web/login?redirect=...` if public) |
| `POST /shop/cart/add`                | jsonrpc  | Return empty-cart payload + warning |
| `POST /shop/cart/quick_add`          | jsonrpc  | Return empty-cart payload + warning |
| `POST /shop/cart/update`             | jsonrpc  | Raise `UserError`               |
| `POST /shop/cart/clear`              | jsonrpc  | Raise `UserError`               |
| `POST /shop/product/is_add_to_cart_allowed` | jsonrpc | Return `False`           |
| `_check_cart(order_sudo)`            | internal | Redirect to `/shop`             |
| Express checkout POST                | jsonrpc  | Raise `UserError`               |
| Express-checkout compute-taxes       | jsonrpc  | Raise `UserError`               |
| `POST /shop/update_address`          | jsonrpc  | Raise `UserError`               |
| `POST /shop/payment/transaction/<id>` | jsonrpc | Raise `ValidationError`         |

The authoritative check used everywhere is
`res.users._ufs_has_wholesale_access()`, which returns True when the
user is internal **or** their partner is in *approved* status.

---

## Troubleshooting

**Signup page returns 404.**
Enable **Free sign up** under *Settings → General Settings →
Permissions*. The extended form only renders when `auth_signup`
accepts public registrations (or the visitor has a signup token).

**"Please upload your Tax Resale Certificate." on signup.**
The file was empty, missing, or larger than 10 MB. Re-select the file
and submit again. Allowed types: PDF, PNG, JPG, JPEG, WEBP.

**An approved user still can't see prices.**
1. On the user form → *Wholesale* tab, confirm **Wholesale Status** is
   *approved* and **Can Buy on Website** shows as True.
2. Clear website assets (*Settings → Technical → User Interface →
   Website → ...* or just refresh). The cart/price visibility is
   evaluated from QWeb on every render, so a hard reload is usually
   enough.
3. Confirm the user isn't logged in as a different session (portal
   sessions can persist across browser tabs).

**Approval email didn't arrive.**
- Check the chatter on the user — `mail.template` failures leave a
  trail there.
- Check **Settings → Technical → Email → Emails** for a failed queue.
- Re-approve from the user form: re-approving an already-approved
  user **does not re-send** the welcome mail. To force a re-send,
  flip the user to *pending* first (Wholesale tab), then *approve*
  again.

**Existing imported customers are locked out.**
The partner default is *approved*, so this should not happen. If a
customer is stuck *pending*, open the partner form and set
*Wholesale Status* to *approved* directly, or approve from the user
form.

**Backend user can't see the "Wholesale" menu.**
The menu requires the **Administration / Settings** group
(`base.group_system`). Grant it under *Settings → Users & Companies
→ Users*.

---

## License

LGPL-3.
