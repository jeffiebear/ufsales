# Chatter Workspace

Technical name: `parameter_chatter_resize` · Author: Parameter · License: LGPL-3

Arrange the form, the chatter and Odoo's document preview for the task at hand.

## What it does

- **Resize** the side chatter by dragging a 6 px handle on its left edge
  (Parameter purple on hover). The form grows into the freed space: Odoo's
  1400 px form width cap is lifted while a custom width is active.
  Double-click the handle (or press Enter on it) to restore the effective
  default width. Keyboard: Left/Right arrows (Shift for larger steps),
  Home/End for the narrowest/widest allowed width.
- **Collapse** the chatter into a slim strip (Data Entry). One click on the
  strip restores the previous layout and width.
- **Float** the chatter in a movable, resizable panel inside the page. The
  panel header shows the current record name and form type, follows record
  navigation and keeps inside the window. Closing it returns the chatter to
  the form.
- **Task layouts** from the chatter's layout button (first icon in the
  chatter's top bar):
  - *Standard*: Odoo's arrangement at your width.
  - *Data Entry*: chatter collapsed, form as wide as possible.
  - *Conversation*: wide chatter while the form keeps at least 560 px.
  - *Review*: an even split of form and chatter; on forms with Odoo's
    document preview (for example vendor bills with a PDF) Odoo's own
    preview layout is kept and the chatter stays open.
  Widths you drag while in Conversation or Review are saved for that layout.
- **Personal preferences** are stored on the server for each user, either
  per form type (default) or as the user's default for every form. They
  follow the user to other browsers. A narrow window never overwrites the
  saved desktop width.
- **Team defaults** for administrators: feature switches, width limits,
  default layout, rules by form and user group with explicit priority, and
  locks.

The module only changes how the chatter is laid out. It never changes who can
read or post messages, never hides messages and never edits records.

## Requirements and support scope

- Odoo 19.0 (branch `19.0`, version `19.0.1.0.1`) and Odoo 20.0 (branch
  `20.0`, version `20.0.1.0.1`). Depends on `mail` only.
- Hosting: Odoo.sh and self-hosted. Not offered for Odoo Online.
- Tested on Odoo 19.0 and 20.0, Community and Enterprise (Enterprise on
  Odoo.sh).
- Desktop browsers with pointer input (tested: Chrome, Firefox). Touch and
  mobile resizing are not claimed. Below 768 px wide the module stays out of
  the way and Odoo's standard chatter is used; the floating panel needs at
  least 992 px.
- Odoo shows the chatter beside the form only from its XXL breakpoint
  (1534 px wide). Below that the chatter sits under the form: collapsing and
  floating still work, side resizing does not apply.

## Installation

1. Copy the `parameter_chatter_resize` folder into an addons path of the
   matching Odoo version (use the `19.0` or `20.0` branch).
2. Restart Odoo, update the apps list and install **Chatter Workspace**, or:

   ```
   odoo-bin -c <your.conf> -d <database> -i parameter_chatter_resize --stop-after-init
   ```

3. Optional: Settings → General Settings → *Chatter Workspace*.

Upgrade: `odoo-bin -c <your.conf> -d <database> -u parameter_chatter_resize --stop-after-init`.

## Use

Open any form with a chatter. The layout button (two-column icon) is the first
button in the chatter's top bar; in the collapsed strip it sits under the
"Chatter" button. The menu lists the layouts allowed by your administrator,
shows which team default applies, and offers:

- *Restore default width*
- *Use this layout on all forms* (copies this form's layout to your default)
- *Reset this form to my defaults*
- *Reset all my layouts…* (asks for confirmation; team defaults apply again)

## Administration

Settings → General Settings → *Chatter Workspace*:

- Features: resizing, collapsing, floating panel, task layouts.
- Personal layouts on/off; remember per form type on/off.
- Width limits (minimum, maximum) and a default width (0 = Odoo's width).
- Team default layout and initial chatter state.
- *Team Defaults* rules (also under Settings → Users & Companies → Chatter
  Workspace): forms, user groups, layout, collapsed state, width, locks.
- *Check a user's effective layout* shows, field by field, where the value
  comes from and which rule won.
- *Reset everyone's layouts* (confirmation required).

### Precedence

Applied field by field (layout, collapsed state, each width):

1. Administrator constraints: disabled features, width limits, locks (the
   global "Personal layouts" switch or the winning rule's locks).
2. The user's layout for this form type.
3. The user's default for all forms.
4. The winning team default rule.
5. The global default in Settings.
6. Odoo's standard layout.

Rules are evaluated by **priority** (lowest number first) and then by
creation order (oldest first). The first rule whose forms and groups match
wins; rules are never merged, and the order of groups never matters. A user
matches a rule's groups when they belong to any of them, including through
implied groups.

All settings apply to the whole database, for every company. Switching the
active company does not change layouts.

## What is stored

- `parameter.chatter.preference`: one row per user and form type (or one row
  for the user's default): layout, collapsed state, widths for Standard,
  Conversation and Review, the floating panel position and size, and the id
  of the browser tab that wrote it last with that tab's write number (used
  only to keep saves in order). A row whose values were all cleared may
  remain empty; it carries no layout and is not listed. No record data,
  message content or drafts are stored.
- `parameter.chatter.rule`: administrator rules.
- `ir.config_parameter` keys starting with `parameter_chatter_resize.`.
- In the browser, `localStorage` key
  `parameter_chatter_workspace:v1:<database>:<user id>` caches the last
  layout received from the server so forms open without flicker. The server
  copy always wins.

Users can only read and change their own preferences; the server enforces
this with access rules and refuses to create or move a preference for
another user. Administrators (Settings access) can review and remove all
preferences.

### When saving fails

Layout changes apply immediately and are saved after a short pause (about
0.6 s), once per change, never on every pointer move and never by polling.
All saves and resets of a browser tab are sent one at a time, in order, and
each carries the tab's id and an increasing number. The server ignores a save
that is older than the one it already stored for the same row, so a slow
request can never bring back an older layout, including when the page is
closed while a save is still in transit (pending changes are then sent with
the page-unload request).

If the save request fails because of a connection problem, the layout stays
active in the current tab, the layout button shows a warning dot, and the
change is sent again with the next change (and once more when the page is
closed). Saves from two different tabs or browsers follow the order in which
they reach the server. If the server refuses a change (for example after an administrator
locked the layout), the module reloads the server's effective layout. If
browser storage is unavailable, only the flicker-free first paint is lost.

## Uninstall

Uninstall from Apps. Odoo drops the preference and rule tables; the module's
settings keys are deleted by the uninstall hook. Browser cache keys become
unused and can be cleared with the browser's site data.

## Known limitations and conflicts

- Do not install alongside another module that resizes, collapses or moves
  the form chatter (for example other "chatter resize/position" apps). Both
  would size the same panel.
- Themes or customizations that restyle the form chatter
  container have not been tested.
- The floating panel stays in the current browser tab; it is not a separate
  window.
- Forms opened in dialogs keep Odoo's standard chatter.

## Support

support@parameterllc.com · https://parameterllc.com/
