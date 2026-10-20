# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
from odoo.tests.common import TransactionCase, new_test_user


class ChatterWorkspaceCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, no_reset_password=True))
        # Each user gets its own e-mail: some databases refuse a second contact
        # with the same e-mail address.
        cls.user_a = new_test_user(
            cls.env, login="pcw_user_a", email="pcw.user.a@example.com", groups="base.group_user")
        cls.user_b = new_test_user(
            cls.env, login="pcw_user_b", email="pcw.user.b@example.com", groups="base.group_user")
        cls.admin = new_test_user(
            cls.env, login="pcw_admin", email="pcw.admin@example.com", groups="base.group_user,base.group_system")
        cls.group_x = cls.env["res.groups"].create({"name": "PCW group X"})
        cls.group_y = cls.env["res.groups"].create({"name": "PCW group Y"})
        cls.Pref = cls.env["parameter.chatter.preference"]
        cls.Rule = cls.env["parameter.chatter.rule"]
        cls.Policy = cls.env["parameter.chatter.policy"]
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.user_model = cls.env["ir.model"]._get("res.users")

    def settings(self, **values):
        current = self.Policy._get_settings()
        current.update(values)
        self.Policy._set_settings(current)

    def config(self, user, model="res.partner"):
        return self.Pref.with_user(user).get_workspace_config(model)

    def save(self, user, values, model="res.partner", scope="model"):
        return self.Pref.with_user(user).save_preference(model, values, scope)
