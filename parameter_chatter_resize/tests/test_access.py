# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..models.compat import set_param
from .common import ChatterWorkspaceCase


@tagged("post_install", "-at_install", "parameter_chatter_resize")
class TestPreferenceIsolation(ChatterWorkspaceCase):
    def setUp(self):
        super().setUp()
        self.save(self.user_a, {"width": 444})
        self.save(self.user_b, {"width": 555})
        self.pref_a = self.Pref.sudo()._get_record(self.user_a, "res.partner")
        self.pref_b = self.Pref.sudo()._get_record(self.user_b, "res.partner")

    def test_each_user_sees_own_layout(self):
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 444)
        self.assertEqual(self.config(self.user_b)["effective"]["width"], 555)

    def test_search_and_read_are_scoped(self):
        found = self.Pref.with_user(self.user_a).search([])
        self.assertEqual(found, self.pref_a)
        self.assertEqual(self.Pref.with_user(self.user_a).search_count([("user_id", "=", self.user_b.id)]), 0)
        with self.assertRaises(AccessError):
            self.pref_b.with_user(self.user_a).read(["width"])

    def test_cannot_write_or_delete_other_users_layout(self):
        with self.assertRaises(AccessError):
            self.pref_b.with_user(self.user_a).write({"width": 300})
        with self.assertRaises(AccessError):
            self.pref_b.with_user(self.user_a).unlink()
        self.assertEqual(self.pref_b.width, 555)

    def test_cannot_create_for_other_user(self):
        with self.assertRaises(AccessError):
            self.Pref.with_user(self.user_a).create({"user_id": self.user_b.id, "model_name": "res.users", "width": 300})

    def test_cannot_move_own_layout_to_other_user(self):
        with self.assertRaises(AccessError):
            self.pref_a.with_user(self.user_a).write({"user_id": self.user_b.id})
        self.assertEqual(self.pref_a.user_id, self.user_a)
        self.assertEqual(self.config(self.user_b)["effective"]["width"], 555)

    def test_public_methods_ignore_client_user(self):
        # There is no user parameter: the methods always act on env.user.
        self.Pref.with_user(self.user_a).reset_preferences("res.partner", "all")
        self.assertTrue(self.pref_b.exists())
        self.assertEqual(self.config(self.user_b)["effective"]["width"], 555)

    def test_admin_can_review_and_reset(self):
        found = self.Pref.with_user(self.admin).search([("user_id", "in", (self.user_a | self.user_b).ids)])
        self.assertEqual(found, self.pref_a | self.pref_b)
        settings = self.env["res.config.settings"].with_user(self.admin).create({})
        settings.action_pcw_reset_all_preferences()
        self.assertFalse(self.Pref.sudo().search([]))

    def test_non_admin_cannot_change_policy(self):
        with self.assertRaises(AccessError):
            self.Rule.with_user(self.user_a).create({"name": "Mine", "lock_layout": True})
        rule = self.Rule.create({"name": "Team"})
        with self.assertRaises(AccessError):
            rule.with_user(self.user_a).write({"lock_layout": True})
        with self.assertRaises(AccessError):
            self.Rule.with_user(self.user_a).search([])
        with self.assertRaises(AccessError):
            self.env["res.config.settings"].with_user(self.user_a).create({"pcw_max_width": 2000})
        with self.assertRaises(AccessError):
            set_param(self.env["ir.config_parameter"].with_user(self.user_a), "parameter_chatter_resize.max_width", "2000")
        with self.assertRaises(AccessError):
            self.env["parameter.chatter.policy.preview"].with_user(self.user_a).create({"user_id": self.user_b.id})
        # The effective configuration only exposes the winning rule's name.
        config = self.config(self.user_a)
        self.assertEqual(set(config["rule"]), {"id", "name"})

    def test_layout_rules_do_not_grant_record_access(self):
        # Layout rules and preferences for a model never grant access to its
        # records: the user still gets Odoo's normal AccessError.
        model = self.env["ir.model"]._get("ir.config_parameter")
        self.Rule.create({"name": "Params", "model_ids": [(6, 0, model.ids)], "layout": "conversation", "lock_layout": False})
        config = self.save(self.user_a, {"layout": "review"}, model="ir.config_parameter")
        self.assertEqual(config["effective"]["layout"], "review")
        with self.assertRaises(AccessError):
            self.env["ir.config_parameter"].with_user(self.user_a).search_read([], ["key"], limit=1)

    def test_preview_wizard_reports_effective_rule(self):
        rule = self.Rule.create({"name": "Partners", "model_ids": [(6, 0, self.partner_model.ids)], "layout": "review", "priority": 3})
        wizard = self.env["parameter.chatter.policy.preview"].with_user(self.admin).create({
            "user_id": self.user_b.id, "model_id": self.partner_model.id,
        })
        self.assertEqual(wizard.rule_id, rule)
        self.assertIn("555", wizard.result_html)
        self.assertIn("Personal layout for this form", wizard.result_html)
