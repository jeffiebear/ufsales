# Copyright 2026 Parameter (https://parameterllc.com/)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).
"""Writes that reach the server out of order (an older request overtaken by a
newer one, e.g. the page-unload request) must never restore an older value."""
from odoo.exceptions import ConcurrencyError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ChatterWorkspaceCase

TAB = "tab-0000-aaaa"
OTHER_TAB = "tab-0000-bbbb"


@tagged("post_install", "-at_install", "parameter_chatter_resize")
class TestWriteOrder(ChatterWorkspaceCase):
    def save_stamped(self, values, seq, model="res.partner", scope="model", tab=TAB, user=None):
        return self.Pref.with_user(user or self.user_a).save_preference(
            model, values, scope, client_session=tab, client_seq=seq)

    def reset_stamped(self, seq, model="res.partner", scope="model", tab=TAB):
        return self.Pref.with_user(self.user_a).reset_preferences(
            model, scope, client_session=tab, client_seq=seq)

    def test_older_write_arriving_late_is_ignored(self):
        self.save_stamped({"width": 600}, seq=2)
        result = self.save_stamped({"width": 400}, seq=1)  # overtaken request
        self.assertTrue(result.get("stale"))
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 600)

    def test_duplicate_write_is_ignored(self):
        self.save_stamped({"width": 600}, seq=3)
        self.assertTrue(self.save_stamped({"width": 600}, seq=3).get("stale"))

    def test_newer_write_applies(self):
        self.save_stamped({"width": 400}, seq=1)
        result = self.save_stamped({"layout": "review"}, seq=2)
        self.assertFalse(result.get("stale"))
        self.assertEqual((result["effective"]["width"], result["effective"]["layout"]), (400, "review"))

    def test_other_tab_is_last_write_wins(self):
        self.save_stamped({"width": 600}, seq=9)
        result = self.save_stamped({"width": 400}, seq=1, tab=OTHER_TAB)
        self.assertFalse(result.get("stale"))
        self.assertEqual(result["effective"]["width"], 400)

    def test_reset_then_late_older_save_cannot_restore_value(self):
        # in-flight save (seq 1) is overtaken by the user's reset (seq 2)
        self.reset_stamped(seq=2)  # nothing stored yet: no row to protect
        self.save_stamped({"width": 450}, seq=3)
        self.reset_stamped(seq=5)
        late = self.save_stamped({"width": 450}, seq=4)  # older than the reset
        self.assertTrue(late.get("stale"))
        config = self.config(self.user_a)
        self.assertEqual((config["effective"]["width"], config["sources"]["width"]), (0, "product"))
        self.assertFalse(config["has_model_override"])

    def test_emptying_by_stamped_save_keeps_a_tombstone(self):
        self.save_stamped({"width": 450}, seq=1)
        self.save_stamped({"width": False}, seq=3)  # double-click reset
        row = self.Pref.sudo()._get_record(self.user_a, "res.partner")
        self.assertTrue(row, "the emptied row must stay to block older writes")
        self.assertFalse(row.has_values)
        self.assertTrue(self.save_stamped({"width": 450}, seq=2).get("stale"))
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 0)
        # Emptied rows are not listed or counted for administrators.
        settings = self.env["res.config.settings"].with_user(self.admin).create({})
        self.assertEqual(settings.pcw_preference_count, 0)

    def test_global_row_is_ordered_whatever_form_wrote_it(self):
        # Two form types write the same global row; the older one arrives last.
        self.save_stamped({"width": 700}, seq=8, model="res.users", scope="global")
        late = self.save_stamped({"width": 500}, seq=7, model="res.partner", scope="global")
        self.assertTrue(late.get("stale"))
        self.assertEqual(self.config(self.user_a, "res.partner")["effective"]["width"], 700)
        self.assertEqual(self.config(self.user_a, "res.users")["effective"]["width"], 700)

    def test_float_geometry_is_ordered(self):
        rect_new = {"left": 100, "top": 90, "width": 500, "height": 600}
        rect_old = {"left": 10, "top": 10, "width": 400, "height": 400}
        self.save_stamped({"float_rect": rect_new}, seq=4, scope="global")
        self.assertTrue(self.save_stamped({"float_rect": rect_old}, seq=3, scope="global").get("stale"))
        self.assertEqual(self.config(self.user_a)["float_rect"], rect_new)

    def test_late_reset_does_not_erase_newer_change(self):
        self.save_stamped({"width": 500}, seq=6)
        self.reset_stamped(seq=5, scope="all")  # reset sent earlier, arrives later
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 500)

    def test_stamps_are_validated(self):
        for session, seq in (("short", 1), (TAB, 0), (TAB, -1), (TAB, "1"), (TAB, True), (123, 1), ("x" * 65, 1)):
            with self.subTest(session=session, seq=seq), self.assertRaises(ValidationError):
                self.save_stamped({"width": 400}, seq=seq, tab=session)

    def test_concurrent_first_insert_is_retried(self):
        self.save_stamped({"width": 400}, seq=1)
        # A second transaction inserting the same (user, model) row would hit
        # the unique index; Odoo retries the request on ConcurrencyError.
        with self.assertRaises(ConcurrencyError), mute_logger("odoo.sql_db"):
            self.Pref.with_user(self.user_a)._create_target({"model_name": "res.partner", "width": 300})

    def test_stamps_never_cross_users(self):
        self.save_stamped({"width": 600}, seq=9)
        result = self.save_stamped({"width": 400}, seq=1, user=self.user_b)
        self.assertFalse(result.get("stale"))
        self.assertEqual(self.config(self.user_a)["effective"]["width"], 600)
        self.assertEqual(self.config(self.user_b)["effective"]["width"], 400)
