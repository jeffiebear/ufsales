# Changelog

## 1.0.0 (unreleased, 2026-10-19)

First release of Chatter Workspace, published separately for Odoo 19.0
(`19.0.1.0.0`) and Odoo 20.0 (`20.0.1.0.0`).

- Side chatter resizing with a 6 px handle on the panel edge, keyboard
  control, double-click/Enter reset to the effective default, and a form that
  grows past Odoo's 1400 px cap.
- Responsive protection: the form keeps at least 560 px; a narrow window
  renders a smaller width without overwriting the saved preference; inline
  styles are removed when Odoo moves the chatter under the form or shows a
  document preview (fixes the stale-width issue of the original script).
- Collapse to a slim strip and restore the previous layout and width.
- Floating chatter panel inside the page with record identity, keyboard
  move/resize and viewport containment.
- Task layouts: Data Entry, Conversation, Review (preview-aware).
- Server-side personal preferences (per form type or global) with
  isolation between users enforced on the server.
- Administrator settings, rules by form and user group with explicit
  priority, locks, an effective-layout checker and a global reset.
- Upgrades on Odoo 20 with Website installed: Website makes the view
  `visibility` column mandatory without a database default, so views created
  by this module during an upgrade were refused. A migration that runs on every
  version change gives the column Website's own default (`public`) for the
  upgrade only and removes it afterwards; it does nothing elsewhere.

Derived from the Odoo 19 "chatter resize" customization written by Parameter
(LGPL-3); identifiers were renamed for this standalone module.
