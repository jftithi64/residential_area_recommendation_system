"""Tests for role-wise menu rights. Run: python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_streamlit as fs  # noqa: E402

sys.modules["streamlit"] = fs.st

import auth  # noqa: E402
import permissions  # noqa: E402
from test_core import TempDB  # noqa: E402


class PermissionTests(TempDB):
    def setUp(self):
        super().setUp()
        self.renter = auth.create_user("Rina", "rina@x.com", "01712345678", "abcd1234", role="renter")
        self.owner = auth.create_user("Omar", "omar@x.com", "01812345678", "abcd1234", role="owner")
        fs.reset()

    def test_defaults(self):
        for role in ("renter", "owner"):
            self.assertEqual(permissions.allowed_pages(role), set(permissions.PAGES))
        self.assertEqual(permissions.allowed_pages("visitor"), {"home"})   # a visitor sees Home only

    def test_save_and_load_per_role(self):
        m = permissions.load_matrix()
        m["renter"]["list_flat"] = False
        m["owner"]["fair_rent"] = False
        permissions.save_matrix(m, "admin@x.com")
        self.assertNotIn("list_flat", permissions.allowed_pages("renter"))
        self.assertIn("list_flat", permissions.allowed_pages("owner"))
        self.assertNotIn("fair_rent", permissions.allowed_pages("owner"))
        self.assertIn("fair_rent", permissions.allowed_pages("renter"))

    def test_locked_pages_and_admin_cannot_be_removed(self):
        m = {r: {k: False for k in permissions.PAGES} for r in permissions.ROLES}
        permissions.save_matrix(m)
        for role in ("renter", "owner"):
            self.assertEqual(permissions.allowed_pages(role), {k for k in permissions.PAGES if permissions.is_locked(k)})
        self.assertEqual(permissions.allowed_pages("visitor"), {"home"})
        self.assertEqual(permissions.allowed_pages("admin"), set(permissions.PAGES))

    def test_reset_restores_defaults(self):
        m = permissions.load_matrix()
        m["renter"]["dashboard"] = False
        permissions.save_matrix(m)
        permissions.reset_defaults()
        self.assertIn("dashboard", permissions.allowed_pages("renter"))

    def test_guard_blocks_hidden_page_for_logged_in_role(self):
        m = permissions.load_matrix()
        m["renter"]["dashboard"] = False
        permissions.save_matrix(m)
        fs.reset()
        fs.st.session_state["user"] = auth.public(auth._find("rina@x.com"))
        with self.assertRaises(fs.StopPage):
            permissions.guard("dashboard")
        permissions.guard("browse")   # still allowed
        fs.st.session_state["user"] = auth.public(auth._find("omar@x.com"))
        permissions.guard("dashboard")   # owner was not restricted

    def test_visitor_gets_login_prompt_on_every_page_except_home(self):
        fs.reset()
        permissions.guard("home")                         # open to visitors
        for key in set(permissions.PAGES) - {"home"}:
            fs.Api.CALLS.clear()
            with self.assertRaises(fs.StopPage):
                permissions.guard(key)
            self.assertIn("page_link", [c[0] for c in fs.Api.CALLS])

    def test_admin_cannot_open_a_page_for_visitors(self):
        m = permissions.load_matrix()
        m["visitor"]["list_flat"] = True                  # an old saved row or a hand edit must not matter
        permissions.save_matrix(m)
        self.assertEqual(permissions.allowed_pages("visitor"), {"home"})
        fs.reset()
        with self.assertRaises(fs.StopPage):
            permissions.guard("list_flat")

    def test_role_change_applies_without_new_login(self):
        m = permissions.load_matrix()
        m["renter"]["dashboard"] = False
        permissions.save_matrix(m)
        fs.reset()
        fs.st.session_state["user"] = auth.public(auth._find("rina@x.com"))
        auth.set_role("rina@x.com", "owner")   # session still says renter; database says owner
        permissions.guard("dashboard")

    def test_menu_rights_page_saves(self):
        import runpy
        auth.set_role("rina@x.com", "admin")
        fs.reset(press=["Save rights"])
        fs.st.session_state["user"] = auth.public(auth._find("rina@x.com"))
        try:
            runpy.run_path(str(ROOT / "views" / "menu_rights.py"), run_name="__page__")
        except (fs.StopPage, fs.RerunPage):
            pass
        self.assertEqual(permissions.allowed_pages("renter"), set(permissions.PAGES))

    def test_menu_rights_page_blocks_non_admin(self):
        import runpy
        fs.reset(press=["Save rights"])
        fs.st.session_state["user"] = auth.public(auth._find("rina@x.com"))
        with self.assertRaises(fs.StopPage):
            runpy.run_path(str(ROOT / "views" / "menu_rights.py"), run_name="__page__")


if __name__ == "__main__":
    unittest.main()
