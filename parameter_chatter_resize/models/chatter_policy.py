# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
"""Effective chatter layout policy.

Precedence, applied field by field (layout, dock state, widths):

1. Enforced administrator constraints: disabled features, width bounds and
   locks (global "personal layouts" switch or the winning rule's locks).
2. The user's personal override for the current model.
3. The user's personal global default.
4. The winning administrator rule (lowest priority number, then lowest id).
5. The global administrator default (Settings).
6. The product fallback (Odoo's standard layout and width).

Only one rule wins for a given user and model; rules are not merged.
All settings are database-wide (stored in ir.config_parameter); they do not
vary by company.
"""

from odoo import _, api, models
from odoo.exceptions import ValidationError

from .compat import get_param, set_param

PARAM_PREFIX = "parameter_chatter_resize."

# Product limits that administrator bounds must stay within.
HARD_MIN_WIDTH = 200
HARD_MAX_WIDTH = 2400
FLOAT_MIN_WIDTH = 320
FLOAT_MIN_HEIGHT = 240
FLOAT_MAX_COORD = 20000

LAYOUTS = ("standard", "conversation", "review", "floating")
DOCK_STATES = ("open", "docked")
WIDTH_FIELDS = ("width", "conversation_width", "review_width")
LAYOUT_FIELDS = ("layout", "dock_state")
PREFERENCE_FIELDS = LAYOUT_FIELDS + WIDTH_FIELDS

# name: (type, product default)
SETTINGS_SPEC = {
    "enable_resize": ("bool", True),
    "enable_dock": ("bool", True),
    "enable_float": ("bool", True),
    "enable_presets": ("bool", True),
    "allow_personal": ("bool", True),
    "remember_per_model": ("bool", True),
    "min_width": ("int", 280),
    "max_width": ("int", 1000),
    "default_width": ("int", 0),
    "default_layout": ("layout", "standard"),
    "default_dock_state": ("dock", "open"),
}

PRODUCT_FALLBACK = {
    "layout": "standard",
    "dock_state": "open",
    "width": 0,
    "conversation_width": 0,
    "review_width": 0,
}


class ParameterChatterPolicy(models.AbstractModel):
    _name = "parameter.chatter.policy"
    _description = "Chatter Workspace policy"

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @api.model
    def _parse_setting(self, kind, raw, default):
        if raw in (None, False, ""):
            return default
        if kind == "bool":
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        if kind == "int":
            try:
                return int(str(raw).strip())
            except ValueError:
                return default
        if kind == "layout":
            return raw if raw in LAYOUTS else default
        if kind == "dock":
            return raw if raw in DOCK_STATES else default
        return default

    @api.model
    def _get_settings(self):
        """Read the database-wide settings, repairing any invalid stored value."""
        params = self.env["ir.config_parameter"].sudo()
        values = {
            name: self._parse_setting(kind, get_param(params, PARAM_PREFIX + name), default)
            for name, (kind, default) in SETTINGS_SPEC.items()
        }
        try:
            self._validate_settings(values)
        except ValidationError:
            # A parameter edited outside the settings screen is out of range:
            # fall back to product bounds rather than breaking every form.
            values["min_width"] = SETTINGS_SPEC["min_width"][1]
            values["max_width"] = SETTINGS_SPEC["max_width"][1]
            if values["default_width"] and not (
                values["min_width"] <= values["default_width"] <= values["max_width"]
            ):
                values["default_width"] = 0
        return values

    @api.model
    def _validate_settings(self, values):
        min_width = values["min_width"]
        max_width = values["max_width"]
        default_width = values["default_width"]
        if not HARD_MIN_WIDTH <= min_width <= HARD_MAX_WIDTH:
            raise ValidationError(
                _("The minimum chatter width must be between %(lo)s and %(hi)s pixels.",
                  lo=HARD_MIN_WIDTH, hi=HARD_MAX_WIDTH)
            )
        if not HARD_MIN_WIDTH <= max_width <= HARD_MAX_WIDTH:
            raise ValidationError(
                _("The maximum chatter width must be between %(lo)s and %(hi)s pixels.",
                  lo=HARD_MIN_WIDTH, hi=HARD_MAX_WIDTH)
            )
        if min_width >= max_width:
            raise ValidationError(_("The minimum chatter width must be smaller than the maximum."))
        if default_width and not min_width <= default_width <= max_width:
            raise ValidationError(
                _("The default chatter width must be empty (Odoo default) or between "
                  "the minimum and maximum widths.")
            )
        if values["default_layout"] not in LAYOUTS:
            raise ValidationError(_("Unknown default layout."))
        if values["default_dock_state"] not in DOCK_STATES:
            raise ValidationError(_("Unknown default chatter state."))

    @api.model
    def _set_settings(self, values):
        self._validate_settings(values)
        params = self.env["ir.config_parameter"].sudo()
        for name, (kind, _default) in SETTINGS_SPEC.items():
            value = values[name]
            if kind == "bool":
                value = "1" if value else "0"
            set_param(params, PARAM_PREFIX + name, str(value))

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    @api.model
    def _find_rule(self, user, model_name):
        """Return the single winning rule for ``user`` on ``model_name``.

        Rules are evaluated by ascending priority then ascending id, so equal
        priorities resolve to the oldest rule. Group order never matters.
        """
        rules = self.env["parameter.chatter.rule"].sudo().search([], order="priority, id")
        user_groups = user.sudo().all_group_ids
        for rule in rules:
            if rule.model_ids and model_name not in rule.model_ids.mapped("model"):
                continue
            if rule.group_ids and not (rule.group_ids & user_groups):
                continue
            return rule
        return self.env["parameter.chatter.rule"]

    # ------------------------------------------------------------------
    # Effective configuration
    # ------------------------------------------------------------------

    @api.model
    def _clamp_width(self, value, settings):
        value = int(value or 0)
        if value <= 0:
            return 0
        return max(settings["min_width"], min(settings["max_width"], value))

    @api.model
    def _preference_values(self, pref):
        if not pref:
            return {}
        values = {}
        for name in LAYOUT_FIELDS:
            if pref[name]:
                values[name] = pref[name]
        for name in WIDTH_FIELDS:
            if pref[name]:
                values[name] = pref[name]
        return values

    @api.model
    def _compute_effective(self, user, model_name):
        """Compute the effective layout for ``user`` on ``model_name``.

        Personal preferences are read for ``user`` only. Callers exposed over
        RPC always pass ``self.env.user``.
        """
        settings = self._get_settings()
        rule = self._find_rule(user, model_name)

        admin = {
            "layout": settings["default_layout"],
            "dock_state": settings["default_dock_state"],
            "width": settings["default_width"],
        }
        admin_sources = {"layout": "settings", "dock_state": "settings", "width": "settings"}
        if rule:
            for name in ("layout", "dock_state"):
                if rule[name]:
                    admin[name] = rule[name]
                    admin_sources[name] = "rule"
            if rule.width:
                admin["width"] = rule.width
                admin_sources["width"] = "rule"

        locked_layout = not settings["allow_personal"] or bool(rule and rule.lock_layout)
        locked_width = (
            not settings["allow_personal"]
            or not settings["enable_resize"]
            or bool(rule and rule.lock_width)
        )

        Preference = self.env["parameter.chatter.preference"].sudo()
        personal_model = Preference._get_record(user, model_name) if model_name else Preference
        personal_global = Preference._get_record(user, False)
        model_values = self._preference_values(personal_model)
        global_values = self._preference_values(personal_global)

        effective = {}
        sources = {}
        for name in PREFERENCE_FIELDS:
            locked = locked_layout if name in LAYOUT_FIELDS else locked_width
            if not locked and name in model_values:
                effective[name], sources[name] = model_values[name], "model"
            elif not locked and name in global_values:
                effective[name], sources[name] = global_values[name], "personal"
            elif name in admin and admin[name]:
                effective[name], sources[name] = admin[name], admin_sources[name]
            else:
                effective[name], sources[name] = PRODUCT_FALLBACK[name], "product"

        # Disabled features win over every stored preference or default.
        if effective["layout"] == "floating" and not settings["enable_float"]:
            effective["layout"], sources["layout"] = "standard", "feature"
        if effective["layout"] in ("conversation", "review") and not settings["enable_presets"]:
            effective["layout"], sources["layout"] = "standard", "feature"
        if effective["dock_state"] == "docked" and not settings["enable_dock"]:
            effective["dock_state"], sources["dock_state"] = "open", "feature"
        for name in WIDTH_FIELDS:
            effective[name] = self._clamp_width(effective[name], settings)

        float_rect = None
        if personal_global and personal_global.float_width and personal_global.float_height:
            float_rect = {
                "left": personal_global.float_left,
                "top": personal_global.float_top,
                "width": personal_global.float_width,
                "height": personal_global.float_height,
            }

        model_label = model_name or ""
        if model_name:
            ir_model = self.env["ir.model"].sudo()._get(model_name)
            if ir_model:
                model_label = ir_model.name

        return {
            "model": model_name or False,
            "model_label": model_label,
            "features": {
                "resize": settings["enable_resize"],
                "dock": settings["enable_dock"],
                "float": settings["enable_float"],
                "presets": settings["enable_presets"],
            },
            "bounds": {"min": settings["min_width"], "max": settings["max_width"]},
            "allow_personal": settings["allow_personal"],
            "remember_per_model": settings["remember_per_model"],
            "locks": {"layout": locked_layout, "width": locked_width},
            "rule": {"id": rule.id, "name": rule.name} if rule else False,
            "admin_default": {
                "layout": admin["layout"],
                "dock_state": admin["dock_state"],
                "width": self._clamp_width(admin["width"], settings),
            },
            "effective": effective,
            "sources": sources,
            "has_model_override": bool(model_values),
            "has_personal_default": bool(global_values),
            "float_rect": float_rect,
        }
