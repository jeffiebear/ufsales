# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, UserError, ValidationError

from .chatter_policy import (
    DOCK_STATES,
    FLOAT_MAX_COORD,
    FLOAT_MIN_HEIGHT,
    FLOAT_MIN_WIDTH,
    HARD_MAX_WIDTH,
    LAYOUT_FIELDS,
    LAYOUTS,
    WIDTH_FIELDS,
)

FLOAT_FIELDS = ("float_left", "float_top", "float_width", "float_height")


class ParameterChatterPreference(models.Model):
    """One user's chatter layout, globally (no model) or for one model.

    Empty fields inherit: a model record falls back to the user's global
    record, which falls back to the administrator defaults. The floating
    panel geometry is only kept on the global record.
    """

    _name = "parameter.chatter.preference"
    _description = "Chatter Workspace personal layout"
    _order = "user_id, model_name"
    _rec_name = "model_name"

    user_id = fields.Many2one(
        "res.users",
        required=True,
        index=True,
        ondelete="cascade",
        default=lambda self: self.env.user,
    )
    model_name = fields.Char(
        string="Form",
        help="Technical model name. Empty for the user's default on every form.",
    )
    layout = fields.Selection(
        [
            ("standard", "Standard"),
            ("conversation", "Conversation"),
            ("review", "Review"),
            ("floating", "Floating panel"),
        ]
    )
    dock_state = fields.Selection([("open", "Open"), ("docked", "Collapsed")], string="Chatter")
    width = fields.Integer(string="Width (px)")
    conversation_width = fields.Integer(string="Conversation Width (px)")
    review_width = fields.Integer(string="Review Width (px)")
    float_left = fields.Integer()
    float_top = fields.Integer()
    float_width = fields.Integer()
    float_height = fields.Integer()
    # Write ordering: the browser tab that last wrote this row and the number
    # of that write. A request from the same tab with a lower number is older
    # than what is stored (it was overtaken in transit) and is ignored.
    client_session = fields.Char(readonly=True, copy=False)
    client_seq = fields.Integer(readonly=True, copy=False)
    has_values = fields.Boolean(compute="_compute_has_values", store=True, index=True)

    _user_model_unique = models.UniqueIndex("(user_id, COALESCE(model_name, ''))")

    # ------------------------------------------------------------------
    # Integrity: a user can never create or move a preference to another user.
    # ------------------------------------------------------------------

    def _is_manager(self):
        return self.env.su or self.env.user.has_group("base.group_system")

    @api.model_create_multi
    def create(self, vals_list):
        if not self._is_manager():
            for vals in vals_list:
                if vals.get("user_id", self.env.uid) != self.env.uid:
                    raise AccessError(_("You can only store your own chatter layout."))
                vals["user_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        if "user_id" in vals and not self._is_manager():
            if vals["user_id"] != self.env.uid or self.user_id != self.env.user:
                raise AccessError(_("You can only store your own chatter layout."))
        return super().write(vals)

    @api.constrains(*WIDTH_FIELDS, *FLOAT_FIELDS)
    def _check_values(self):
        for pref in self:
            for name in WIDTH_FIELDS:
                if not 0 <= pref[name] <= HARD_MAX_WIDTH:
                    raise ValidationError(_("Chatter widths must be between 0 and %(max)s pixels.", max=HARD_MAX_WIDTH))
            for name in FLOAT_FIELDS:
                if not -FLOAT_MAX_COORD <= pref[name] <= FLOAT_MAX_COORD:
                    raise ValidationError(_("The floating panel position is out of range."))

    @api.constrains("model_name")
    def _check_model_name(self):
        for pref in self:
            if pref.model_name and pref.model_name not in self.env:
                raise ValidationError(_("Unknown model %(model)s.", model=pref.model_name))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_record(self, user, model_name):
        return self.search(
            [("user_id", "=", user.id), ("model_name", "=", model_name or False)], limit=1
        )

    @api.model
    def _check_client_order(self, client_session, client_seq):
        """Validate the optional write-order stamp sent by the web client."""
        if not client_session and not client_seq:
            return False, 0
        if (
            not isinstance(client_session, str)
            or not 8 <= len(client_session) <= 64
            or isinstance(client_seq, bool)
            or not isinstance(client_seq, int)
            or client_seq < 1
        ):
            raise ValidationError(_("Invalid write order."))
        return client_session, client_seq

    def _is_newer_than(self, client_session, client_seq):
        """True when this row already holds a later write from the same tab."""
        self.ensure_one()
        return bool(client_session) and self.client_session == client_session and self.client_seq >= client_seq

    @api.model
    def _create_target(self, vals):
        """Create a preference row; a concurrent insert of the same row makes
        Odoo retry the whole request instead of failing it."""
        try:
            with self.env.cr.savepoint():
                return self.create(vals)
        except psycopg2.IntegrityError as exc:
            if getattr(exc, "pgcode", None) == "23505":  # unique_violation
                raise ConcurrencyError("Concurrent chatter layout save, retrying") from exc
            raise

    @api.model
    def _check_model_arg(self, model_name):
        if model_name in (None, False, ""):
            return False
        if not isinstance(model_name, str) or model_name not in self.env:
            raise ValidationError(_("Unknown model."))
        return model_name

    @api.model
    def _sanitize(self, values, config, scope):
        """Validate client values against the effective policy.

        ``None``/``False`` clears a field (inherit). Widths are clamped to the
        administrator bounds; values a correct client never sends (locked or
        disabled features, unknown keys, absurd numbers) raise an error.
        """
        if not isinstance(values, dict):
            raise ValidationError(_("Invalid chatter layout."))
        allowed = set(LAYOUT_FIELDS + WIDTH_FIELDS)
        if scope == "global":
            allowed.add("float_rect")
        unknown = set(values) - allowed
        if unknown:
            raise ValidationError(_("Unsupported chatter layout fields: %(fields)s", fields=", ".join(sorted(unknown))))
        features, locks, bounds = config["features"], config["locks"], config["bounds"]
        clean = {}
        for name, value in values.items():
            if name in LAYOUT_FIELDS and value and locks["layout"]:
                raise UserError(_("Your administrator has set the chatter layout for this form."))
            if name in WIDTH_FIELDS and value and locks["width"]:
                raise UserError(_("Your administrator has set the chatter width for this form."))
            if name == "layout":
                if value and value not in LAYOUTS:
                    raise ValidationError(_("Unknown chatter layout."))
                if value == "floating" and not features["float"]:
                    raise UserError(_("The floating chatter panel is disabled."))
                if value in ("conversation", "review") and not features["presets"]:
                    raise UserError(_("Task layouts are disabled."))
                clean[name] = value or False
            elif name == "dock_state":
                if value and value not in DOCK_STATES:
                    raise ValidationError(_("Unknown chatter state."))
                if value == "docked" and not features["dock"]:
                    raise UserError(_("Collapsing the chatter is disabled."))
                clean[name] = value or False
            elif name in WIDTH_FIELDS:
                if value in (None, False):
                    clean[name] = 0
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValidationError(_("Chatter widths must be numbers."))
                if value < 0 or value > HARD_MAX_WIDTH:
                    raise ValidationError(_("Chatter widths must be between 0 and %(max)s pixels.", max=HARD_MAX_WIDTH))
                width = int(round(value))
                clean[name] = max(bounds["min"], min(bounds["max"], width)) if width else 0
            elif name == "float_rect":
                if value in (None, False):
                    clean.update(dict.fromkeys(FLOAT_FIELDS, 0))
                    continue
                if not features["float"]:
                    raise UserError(_("The floating chatter panel is disabled."))
                if not isinstance(value, dict) or set(value) != {"left", "top", "width", "height"}:
                    raise ValidationError(_("Invalid floating panel geometry."))
                rect = {}
                for key, number in value.items():
                    if isinstance(number, bool) or not isinstance(number, (int, float)):
                        raise ValidationError(_("Invalid floating panel geometry."))
                    if abs(number) > FLOAT_MAX_COORD:
                        raise ValidationError(_("The floating panel position is out of range."))
                    rect[key] = int(round(number))
                clean.update({
                    "float_left": rect["left"],
                    "float_top": rect["top"],
                    "float_width": max(FLOAT_MIN_WIDTH, rect["width"]),
                    "float_height": max(FLOAT_MIN_HEIGHT, rect["height"]),
                })
        return clean

    @api.depends(*LAYOUT_FIELDS, *WIDTH_FIELDS, *FLOAT_FIELDS)
    def _compute_has_values(self):
        for pref in self:
            pref.has_values = not pref._is_empty()

    def _is_empty(self):
        self.ensure_one()
        return not any(self[name] for name in LAYOUT_FIELDS + WIDTH_FIELDS + FLOAT_FIELDS)

    def _clear_values(self):
        return dict.fromkeys(LAYOUT_FIELDS, False) | dict.fromkeys(WIDTH_FIELDS + FLOAT_FIELDS, 0)

    # ------------------------------------------------------------------
    # Public API for the web client (always scoped to the current user)
    # ------------------------------------------------------------------

    @api.model
    def get_workspace_config(self, model_name=False):
        """Return the current user's effective chatter layout for a form."""
        model_name = self._check_model_arg(model_name)
        return self.env["parameter.chatter.policy"]._compute_effective(self.env.user, model_name)

    @api.model
    def save_preference(self, model_name, values, scope="model", client_session=False, client_seq=0):
        """Store part of the current user's layout and return the new config.

        :param model_name: technical model of the form, or False
        :param values: subset of layout/dock_state/width/conversation_width/
            review_width (and float_rect for the global scope)
        :param scope: "model" for this form type, "global" for every form
        :param client_session: id of the browser tab sending the change
        :param client_seq: increasing number of the write within that tab.
            When given, a write older than the one already stored for the same
            target from the same tab is ignored (the result has "stale": True),
            and emptied rows are kept so an older write cannot recreate them.
        """
        if scope not in ("model", "global"):
            raise ValidationError(_("Unknown preference scope."))
        model_name = self._check_model_arg(model_name)
        if scope == "model" and not model_name:
            raise ValidationError(_("A model is required for a form-specific layout."))
        client_session, client_seq = self._check_client_order(client_session, client_seq)
        policy = self.env["parameter.chatter.policy"]
        config = policy._compute_effective(self.env.user, model_name)
        if not config["allow_personal"] and set(values) - {"float_rect"}:
            raise UserError(_("Personal chatter layouts are disabled by your administrator."))
        clean = self._sanitize(values, config, scope)
        target_model = model_name if scope == "model" else False
        pref = self._get_record(self.env.user, target_model)
        if pref and pref._is_newer_than(client_session, client_seq):
            return dict(policy._compute_effective(self.env.user, model_name), stale=True)
        stamp = {"client_session": client_session, "client_seq": client_seq} if client_session else {}
        if pref:
            pref.write(dict(clean, **stamp))
        elif any(clean.values()) or stamp:
            pref = self._create_target(dict(clean, model_name=target_model, **stamp))
        if pref and not client_session and pref._is_empty():
            pref.unlink()
        return policy._compute_effective(self.env.user, model_name)

    @api.model
    def reset_preferences(self, model_name=False, scope="model", client_session=False, client_seq=0):
        """Forget the current user's layouts.

        scope "model": this form type returns to the user's own defaults.
        scope "personal": the user's global default is cleared (form-specific
        layouts are kept).
        scope "all": every personal layout of the user is removed, so team
        defaults apply everywhere.

        With a write-order stamp, rows are emptied rather than deleted (so an
        older write still in transit cannot bring a value back), and rows that
        already hold a later write from the same tab are left alone.
        """
        model_name = self._check_model_arg(model_name)
        client_session, client_seq = self._check_client_order(client_session, client_seq)
        domain = [("user_id", "=", self.env.uid)]
        if scope == "model":
            if not model_name:
                raise ValidationError(_("A model is required to reset a form layout."))
            domain.append(("model_name", "=", model_name))
        elif scope == "personal":
            domain.append(("model_name", "=", False))
        elif scope != "all":
            raise ValidationError(_("Unknown reset scope."))
        prefs = self.search(domain)
        if client_session:
            for pref in prefs:
                if not pref._is_newer_than(client_session, client_seq):
                    pref.write(dict(pref._clear_values(), client_session=client_session, client_seq=client_seq))
        else:
            prefs.unlink()
        return self.env["parameter.chatter.policy"]._compute_effective(self.env.user, model_name)
