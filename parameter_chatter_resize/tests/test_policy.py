# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.compat import set_param
from .common import ChatterWorkspaceCase


@tagged("post_install", "-at_install", "parameter_chatter_resize")
class TestSettingsValidation(ChatterWorkspaceCase):
    def test_product_defaults(self):
        config = self.config(self.user_a)
        self.assertEqual(config["bounds"], {"min": 280, "max": 1000})
        self.assertEqual(config["effective"]["layout"], "standard")
        self.assertEqual(config["effective"]["dock_state"], "open")
        self.assertEqual(config["effective"]["width"], 0)
        self.assertEqual(config["sources"]["width"], "product")
        self.assertTrue(all(config["features"].values()))
        self.assertFalse(config["rule"])

    def test_invalid_bounds_rejected(self):
        for values in (
            {"min_width": 100},  # below the product minimum
            {"max_width": 5000},  # above the product maximum
            {"min_width": 600, "max_width": 500},  # min >= max
            {"min_width": 300, "max_width": 900, "default_width": 950},  # default outside bounds
            {"default_layout": "sideways"},
            {"default_dock_state": "maybe"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.settings(**values)

    def test_settings_form_validates(self):
        settings = self.env["res.config.settings"].with_user(self.admin).create(
            {"pcw_min_width": 700, "pcw_max_width": 400}
        )
        with self.assertRaises(ValidationError):
            settings.execute()

    def test_settings_form_round_trip(self):
        settings = self.env["res.config.settings"].with_user(self.admin).create({
            "pcw_min_width": 300,
            "pcw_max_width": 800,
            "pcw_default_width": 500,
            "pcw_enable_float": False,
            "pcw_default_layout": "conversation",
            "pcw_default_dock_state": "open",
        })
        settings.execute()
        values = self.Policy._get_settings()
        self.assertEqual((values["min_width"], values["max_width"], values["default_width"]), (300, 800, 500))
        self.assertFalse(values["enable_float"])
        self.assertTrue(values["enable_dock"])  # untouched booleans keep their value
        fresh = self.env["res.config.settings"].with_user(self.admin).create({})
        self.assertEqual(fresh.pcw_default_layout, "conversation")
        self.assertFalse(fresh.pcw_enable_float)

    def test_corrupt_parameter_falls_back(self):
        params = self.env["ir.config_parameter"].sudo()
        set_param(params, "parameter_chatter_resize.min_width", "5")
        set_param(params, "parameter_chatter_resize.max_width", "not a number")
        config = self.config(self.user_a)
        self.assertEqual(config["bounds"], {"min": 280, "max": 1000})

    def test_widths_are_clamped_to_bounds(self):
        self.settings(min_width=300, max_width=600)
        config = self.save(self.user_a, {"width": 900})
        self.assertEqual(config["effective"]["width"], 600)
        config = self.save(self.user_a, {"width": 250})
        self.assertEqual(config["effective"]["width"], 300)
        # Narrowing bounds later also clamps stored widths on read.
        self.save(self.user_a, {"width": 590})
        self.settings(min_width=300, max_width=450)
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 450)

    def test_invalid_values_rejected(self):
        for values in (
            {"width": -10},
            {"width": 99999},
            {"width": "400"},
            {"width": True},
            {"layout": "sideways"},
            {"dock_state": "half"},
            {"float_rect": {"left": 1, "top": 1, "width": 400, "height": 300}},  # global only
            {"user_id": self.user_b.id},
            {"unknown": 1},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.save(self.user_a, values)
        with self.assertRaises(ValidationError):
            self.save(self.user_a, {"width": 400}, model="no.such.model")
        with self.assertRaises(ValidationError):
            self.save(self.user_a, {"width": 400}, scope="everyone")


@tagged("post_install", "-at_install", "parameter_chatter_resize")
class TestPolicyPrecedence(ChatterWorkspaceCase):
    def test_full_precedence_chain(self):
        # product fallback
        self.assertEqual(self.config(self.user_a)["sources"]["layout"], "settings")
        # global admin default
        self.settings(default_layout="review", default_width=450)
        config = self.config(self.user_a)
        self.assertEqual(config["effective"]["layout"], "review")
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (450, "settings"))
        # matching rule beats global settings
        self.Rule.create({"name": "Partners", "model_ids": [(6, 0, self.partner_model.ids)], "layout": "conversation", "width": 500})
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["layout"], config["sources"]["layout"]), ("conversation", "rule"))
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (500, "rule"))
        self.assertEqual(config["rule"]["name"], "Partners")
        # personal global beats the rule
        self.save(self.user_a, {"layout": "standard", "width": 600}, model="res.partner", scope="global")
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["layout"], config["sources"]["layout"]), ("standard", "personal"))
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (600, "personal"))
        # personal model override beats personal global, field by field
        self.save(self.user_a, {"width": 700})
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (700, "model"))
        self.assertEqual(config["sources"]["layout"], "personal")
        # the override is specific to the model
        other = self.config(self.user_a, model="res.users")
        self.assertEqual((other["effective"]["width"], other["sources"]["width"]), (600, "personal"))
        # resets
        config = self.Pref.with_user(self.user_a).reset_preferences("res.partner", "model")
        self.assertEqual(config["sources"]["width"], "personal")
        config = self.Pref.with_user(self.user_a).reset_preferences("res.partner", "all")
        self.assertEqual(config["sources"]["width"], "rule")

    def test_reset_width_keeps_other_preferences(self):
        self.save(self.user_a, {"layout": "conversation", "dock_state": "docked", "width": 640, "conversation_width": 720})
        config = self.save(self.user_a, {"conversation_width": False})
        self.assertEqual(config["effective"]["layout"], "conversation")
        self.assertEqual(config["effective"]["dock_state"], "docked")
        self.assertEqual(config["effective"]["width"], 640)
        self.assertEqual(config["effective"]["conversation_width"], 0)

    def test_rule_priority_and_tie_breaker(self):
        self.user_a.group_ids = [(4, self.group_x.id), (4, self.group_y.id)]
        r_y = self.Rule.create({"name": "Y", "priority": 5, "group_ids": [(6, 0, self.group_y.ids)], "layout": "review"})
        r_x = self.Rule.create({"name": "X", "priority": 5, "group_ids": [(6, 0, self.group_x.ids)], "layout": "conversation"})
        # same priority: the older rule (lower id) wins, whatever the group order
        self.assertLess(r_y.id, r_x.id)
        self.assertEqual(self.config(self.user_a)["rule"]["id"], r_y.id)
        r_x.priority = 1
        config = self.config(self.user_a)
        self.assertEqual((config["rule"]["id"], config["effective"]["layout"]), (r_x.id, "conversation"))
        # archived rules are ignored
        r_x.active = False
        self.assertEqual(self.config(self.user_a)["rule"]["id"], r_y.id)
        # only one rule applies: fields left empty on the winner come from settings
        self.assertEqual(self.config(self.user_a)["sources"]["dock_state"], "settings")

    def test_rule_matching_by_model_and_group(self):
        rule = self.Rule.create({
            "name": "Users in X on contacts",
            "model_ids": [(6, 0, self.partner_model.ids)],
            "group_ids": [(6, 0, self.group_x.ids)],
            "dock_state": "docked",
        })
        self.assertFalse(self.config(self.user_a)["rule"])  # not in group X
        self.user_a.group_ids = [(4, self.group_x.id)]
        self.assertEqual(self.config(self.user_a)["rule"]["id"], rule.id)
        self.assertFalse(self.config(self.user_a, model="res.users")["rule"])  # other model
        # implied groups count
        self.user_b.group_ids = [(4, self.group_y.id)]
        self.group_y.implied_ids = [(4, self.group_x.id)]
        self.assertEqual(self.config(self.user_b)["rule"]["id"], rule.id)

    def test_locks(self):
        self.Rule.create({"name": "Locked", "layout": "review", "width": 420, "lock_layout": True, "lock_width": True})
        with self.assertRaises(UserError):
            self.save(self.user_a, {"layout": "standard"})
        with self.assertRaises(UserError):
            self.save(self.user_a, {"dock_state": "docked"})
        with self.assertRaises(UserError):
            self.save(self.user_a, {"width": 500})
        # A preference stored before the lock is ignored while the lock exists.
        self.env["parameter.chatter.preference"].create({"user_id": self.user_a.id, "model_name": "res.partner", "layout": "floating", "width": 900})
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["layout"], config["sources"]["layout"]), ("review", "rule"))
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (420, "rule"))
        self.assertEqual(config["locks"], {"layout": True, "width": True})
        # The float panel geometry is not a layout choice and stays allowed.
        self.save(self.user_a, {"float_rect": {"left": 10, "top": 20, "width": 400, "height": 500}}, scope="global")

    def test_personal_layouts_disabled(self):
        self.save(self.user_a, {"layout": "conversation"})
        self.settings(allow_personal=False)
        config = self.config(self.user_a)
        self.assertEqual(config["effective"]["layout"], "standard")
        self.assertEqual(config["locks"], {"layout": True, "width": True})
        with self.assertRaises(UserError):
            self.save(self.user_a, {"layout": "review"})

    def test_disabled_features_fall_back(self):
        self.save(self.user_a, {"layout": "floating", "dock_state": "docked", "width": 500, "review_width": 600})
        self.settings(enable_float=False, enable_dock=False, enable_resize=False)
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["layout"], config["sources"]["layout"]), ("standard", "feature"))
        self.assertEqual((config["effective"]["dock_state"], config["sources"]["dock_state"]), ("open", "feature"))
        self.assertEqual(config["effective"]["width"], 0)  # personal width ignored without resizing
        self.assertTrue(config["locks"]["width"])
        with self.assertRaises(UserError):
            self.save(self.user_a, {"layout": "floating"})
        with self.assertRaises(UserError):
            self.save(self.user_a, {"dock_state": "docked"})
        self.settings(enable_float=True, enable_dock=True, enable_resize=True, enable_presets=False)
        with self.assertRaises(UserError):
            self.save(self.user_a, {"layout": "review"})
        self.assertEqual(self.config(self.user_a)["effective"]["layout"], "floating")
        self.save(self.user_a, {"layout": False})
        self.save(self.user_a, {"layout": "standard"}, scope="global")
        self.env["parameter.chatter.preference"].sudo()._get_record(self.user_a, "res.partner").layout = "conversation"
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["layout"], config["sources"]["layout"]), ("standard", "feature"))

    def test_remember_per_model_flag_is_reported(self):
        self.settings(remember_per_model=False)
        self.assertFalse(self.config(self.user_a)["remember_per_model"])

    def test_empty_preference_is_removed(self):
        self.save(self.user_a, {"width": 500})
        self.save(self.user_a, {"width": False})
        self.assertFalse(self.Pref.sudo().search([("user_id", "=", self.user_a.id)]))

    def test_company_switch_does_not_change_layout(self):
        company_2 = self.env["res.company"].create({"name": "PCW Second Company"})
        self.user_a.write({"company_ids": [(4, company_2.id)]})
        self.save(self.user_a, {"width": 515})
        self.Rule.create({"name": "All", "layout": "review"})
        main = self.Pref.with_user(self.user_a).with_context(allowed_company_ids=self.user_a.company_id.ids).get_workspace_config("res.partner")
        other = self.Pref.with_user(self.user_a).with_context(allowed_company_ids=company_2.ids).get_workspace_config("res.partner")
        self.assertEqual(main, other)
        self.assertEqual(other["effective"]["width"], 515)
