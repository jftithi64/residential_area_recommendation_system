"""Run every page script against a temporary database with a fake streamlit, and check the main actions work."""
import os
import runpy
import sys
from pathlib import Path
from unittest import mock

import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_streamlit as fs  # noqa: E402

sys.modules["streamlit"] = fs.st

import db  # noqa: E402
import listing_logic  # noqa: E402
import permissions  # noqa: E402
import recommender  # noqa: E402
from test_core import TempDB  # noqa: E402


def run_page(name):
    try:
        runpy.run_path(str(ROOT / "views" / f"{name}.py"), run_name="__page__")
    except (fs.StopPage, fs.RerunPage):
        pass


class PageTests(TempDB):
    def setUp(self):
        super().setUp()
        with db.connect() as con:
            con.executemany("INSERT INTO location_coords VALUES (?,?,?,?,?)",
                            [("Mirpur", "", 23.8069, 90.3687, "m"), ("Uttara", "", 23.8759, 90.3795, "m"),
                             ("Kafrul", "", 23.7960, 90.3830, "m"), ("Dhanmondi", "", 23.7461, 90.3742, "m")])
            con.executemany("INSERT INTO landmarks(name, kind, area, lat, lon, coord_source) VALUES (?,?,?,?,?,?)",
                            [("Test University", "university", "Uttara", 23.8759, 90.3795, "osm"),
                             ("Test School", "school", "Mirpur", 23.8100, 90.3700, "osm"),
                             ("Mirpur", "area", "Mirpur", 23.8069, 90.3687, "manual_centroid")])
        for i in range(1, 31):
            self.add_base(i, ["Mirpur", "Uttara", "Dhanmondi"][i % 3], price=12000 + 700 * i, fair_rent=20000)
        p = mock.patch.object(recommender, "predict_fair_rent", lambda *a, **k: 20000.0)
        p.start()
        self.addCleanup(p.stop)
        fs.reset()

    def tearDown(self):
        super().tearDown()

    def test_static_pages_run(self):
        for page in ("start", "about", "dashboard"):
            fs.reset()
            self._login_as("renter")
            run_page(page)

    def test_visitor_home_page_has_numbers_reviews_and_no_search(self):
        import auth
        uid = auth.create_user("Rina Akter", "rina@x.com", "01912345678", "abcd1234")
        db.save_review(uid, "Rina", "renter", 5, "Found a flat near my office in two days.")
        fs.reset()
        run_page("start")                                   # nobody is logged in
        shown = [c[0] for c in fs.Api.CALLS]
        self.assertNotIn("form", shown)                      # no search form for a visitor
        html = " ".join(str(c[1]) for c in fs.Api.CALLS if c[0] == "markdown")
        heads = " ".join(str(c[1]) for c in fs.Api.CALLS if c[0] == "subheader")
        self.assertIn("Log in to search flats", heads)
        self.assertIn("Found a flat near my office", html)
        self.assertNotIn("🔒", html + heads)                 # no lock signs for a visitor
        links = [str(c[1]) for c in fs.Api.CALLS if c[0] == "page_link"]
        self.assertEqual(len(links), 2)                      # one Log in and one Sign up, nothing else
        self.assertEqual(db.count_users(), 1)

    def test_visitor_cannot_open_search_or_listing_pages(self):
        for key in ("browse", "fair_rent", "find", "list_flat", "dashboard", "add_photos", "my_listing"):
            fs.reset()
            with self.assertRaises(fs.StopPage):
                permissions.guard(key)

    def test_signup_verify_twice_still_creates_account(self):
        import auth
        from unittest import mock
        with mock.patch.dict(os.environ, {"DEMO_OTP": "1"}), mock.patch.object(auth, "smtp_configured", lambda: False):
            ok, _, code = auth.start_email_otp("new@x.com")
        self.assertTrue(ok)
        fs.reset({"6-digit code": code}, press=["Verify and create account"])
        fs.st.session_state["signup_pending"] = {"full_name": "New Person", "email": "new@x.com", "phone": "01712345670",
                                                 "password": "abcd1234", "role": "renter", "interests": {"purposes": []}}
        run_page("signup")                       # first run: code right, account made
        fs.st.session_state.pop("user", None)    # pretend that run was cut off before it finished
        fs.st.session_state["signup_pending"] = {"full_name": "New Person", "email": "new@x.com", "phone": "01712345670",
                                                 "password": "abcd1234", "role": "renter", "interests": {"purposes": []}}
        run_page("signup")                       # second run: must not say "No code was sent"
        self.assertIsNotNone(auth._find("new@x.com"))

    def test_signup_with_existing_email_shows_login_screen_not_code_form(self):
        import auth
        auth.create_user("Old", "old@x.com", "01712345673", "abcd1234")
        fs.reset({"6-digit code": "123456"}, press=["Verify and create account"])
        fs.st.session_state["signup_pending"] = {"full_name": "Old", "email": "old@x.com", "phone": "01712345673",
                                                 "password": "abcd1234", "role": "renter", "interests": {"purposes": []}}
        run_page("signup")
        self.assertNotIn("signup_pending", fs.st.session_state)
        self.assertEqual(fs.st.session_state["signup_existing"], "old@x.com")
        self.assertIsNone(fs.st.session_state.get("user"))

    def test_signup_logs_in_and_home_shows_success_message(self):
        import auth
        from unittest import mock
        with mock.patch.dict(os.environ, {"DEMO_OTP": "1"}), mock.patch.object(auth, "smtp_configured", lambda: False):
            ok, _, code = auth.start_email_otp("fresh@x.com")
        fs.reset({"6-digit code": code}, press=["Verify and create account"])
        fs.st.session_state["signup_pending"] = {"full_name": "Fresh Person", "email": "fresh@x.com", "phone": "01712345672",
                                                 "password": "abcd1234", "role": "renter", "interests": {"purposes": []}}
        run_page("signup")
        self.assertEqual(fs.st.session_state["user"]["email"], "fresh@x.com")   # logged in automatically
        self.assertTrue(fs.st.session_state["goto_home_once"])
        fs.Api.CALLS.clear()
        run_page("start")
        self.assertIn("success", [c[0] for c in fs.Api.CALLS])
        self.assertNotIn("account_created", fs.st.session_state)

    def test_owner_flat_is_shown_even_when_it_ranks_below_the_top_24(self):
        i = db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=800, bed=2, bath=2,
                                price=29900, fair_rent=29900, status="approved"))
        fs.reset({"Highest rent a month (৳)": 30000, "Measure real road distance (needs internet)": False},
                 press=["Show flats"])
        self._login_as("renter")
        run_page("browse")
        shown = fs.st.session_state["browse_df"]
        self.assertIn(i, shown.listing_id.tolist())
        self.assertEqual(int(shown.iloc[0].listing_id), i)          # owner-confirmed flats come first
        self.assertGreater(fs.st.session_state["browse_total"], len(shown) - 1)

    def test_login_reruns_instead_of_switching_to_a_page_the_visitor_menu_lacks(self):
        import auth
        auth.create_user("Rina", "rina@x.com", "01712345671", "abcd1234")
        fs.reset({"Email or mobile number": "rina@x.com", "Password": "abcd1234"}, press=["Log in"])
        run_page("login")
        self.assertEqual(fs.st.session_state.get("after_login"), "browse")
        self.assertIsNotNone(fs.st.session_state.get("user"))

    def test_forgot_password_page_flow(self):
        import auth
        auth._env = lambda name: "1" if name == "DEMO_OTP" else ""
        self.addCleanup(setattr, auth, "_env", auth._env)
        auth.create_user("Rina", "rina@x.com", "01712345671", "oldpass123")
        fs.reset(press=["Forgot password?"])
        run_page("login")
        self.assertTrue(fs.st.session_state.get("reset_mode"))
        fs.Api.PRESS = {"Send code"}
        fs.Api.ANSWERS = {"Email": "rina@x.com"}
        run_page("login")
        self.assertEqual(fs.st.session_state.get("reset_email"), "rina@x.com")
        code = fs.st.session_state["reset_demo_code"]
        fs.Api.PRESS = {"Change password"}
        fs.Api.ANSWERS = {"6-digit code": code, "New password": "newpass123", "Repeat new password": "newpass123"}
        run_page("login")
        self.assertIn("password has been changed", fs.st.session_state.get("reset_done", ""))
        self.assertIsNotNone(auth.authenticate("rina@x.com", "newpass123")[0])

    def test_dashboard_shows_reviews(self):
        import auth
        uid = auth.create_user("Rina", "rina@x.com", "01712345671", "abcd1234")
        db.save_review(uid, "Rina", "renter", 4, "Useful rent check, easy to use.")
        fs.reset()
        self._login_as("renter")
        run_page("dashboard")
        html = " ".join(str(c[1]) for c in fs.Api.CALLS if c[0] == "markdown")
        self.assertIn("Useful rent check", html)

    def test_account_page_saves_a_review(self):
        fs.reset({"Your review": "Clear and easy to use, rent check was helpful."}, press=["Save review"])
        self._login_as("renter")
        run_page("account")
        r = db.latest_reviews()
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["rating"], 5)
        self.assertIn("rent check", r[0]["comment"])

    def test_find_without_search(self):
        self._login_as("renter")
        run_page("find")

    def test_find_search_with_destination(self):
        fs.reset({"Search university": "Test University", "Type of place": "University"}, press=["Find flats"])
        self._login_as("renter")
        run_page("find")
        pool = fs.st.session_state["pool"]
        self.assertFalse(pool.empty)
        self.assertTrue((pool.Price <= 25000).all())
        self.assertIn("ranked", fs.st.session_state)
        self.assertTrue(fs.st.session_state["ranked"].km.notna().any())

    def test_find_search_with_vehicle(self):
        fs.reset({"Search university": "Test University", "Type of place": "University", "Vehicle": "rickshaw",
                  "Walk if closer than (km)": 0.0}, press=["Find flats"])
        self._login_as("renter")
        run_page("find")
        pool = fs.st.session_state["pool"]
        self.assertFalse(pool.empty)
        self.assertEqual(set(pool.vehicle), {"Rickshaw"})
        self.assertEqual(fs.st.session_state["search"]["vehicle"], "Rickshaw")
        self.assertTrue((pool.travel_cost > 0).any())

    def test_find_search_no_destination_and_survey_answer(self):
        fs.reset(press=["Find flats"])
        self._login_as("renter")
        run_page("find")
        pair = fs.st.session_state["pair"]
        self.assertIsNotNone(pair)
        fs.st.session_state["pool"]  # exists
        # simulate pressing "I prefer A": run the callback the page registered
        import runpy as _r
        ns = _r.run_path(str(ROOT / "views" / "find.py"), run_name="__page__")
        ns["record"](1)
        self.assertEqual(len(db.pairs_df()), 1)

    def test_find_no_match_message(self):
        fs.reset({"Highest rent you can pay (৳ / month)": 1000}, press=["Find flats"])
        self._login_as("renter")
        run_page("find")
        self.assertTrue(fs.st.session_state["pool"].empty)

    def test_list_flat_requires_area(self):
        self._login_as("renter")
        run_page("list_flat")                      # no area chosen: page stops politely

    def test_list_flat_submit_creates_pending_listing(self):
        fs.reset({"Area": "Mirpur", "I agree that the details above are stored and (if ticked) shown, as explained "
                  "on the About and privacy page.": True, "Phone or email (optional)": "017000"},
                 press=["Submit for review"])
        self._login_as("renter")
        run_page("list_flat")
        rows = db.load_listings(include_private=True)
        mine = rows[rows.is_extra == 1]
        self.assertEqual(len(mine), 1)
        r = mine.iloc[0]
        self.assertEqual((r.status, r.Place, r.entry_kind), ("pending", "Mirpur", "available"))
        self.assertTrue(listing_logic.hash_code("x") != r.edit_code_hash)
        self.assertEqual(r.contact_public, 0)

    def test_list_flat_without_consent_is_rejected(self):
        fs.reset({"Area": "Mirpur"}, press=["Submit for review"])
        self._login_as("renter")
        run_page("list_flat")
        self.assertEqual(int((db.load_listings().is_extra == 1).sum()), 0)

    def test_manage_listing_flow(self):
        code = listing_logic.make_edit_code()
        i = db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=900, bed=2, bath=2,
                                price=20000, fair_rent=20000, status="approved",
                                edit_code_hash=listing_logic.hash_code(code)))
        fs.reset({"Listing number": i, "Edit code": "wrong"}, press=["Open my listing"])
        self._login_as("renter")
        run_page("my_listing")
        self.assertNotIn("owned", fs.st.session_state)
        fs.reset({"Listing number": i, "Edit code": code}, press=["Open my listing"])
        self._login_as("renter")
        run_page("my_listing")
        self.assertEqual(fs.st.session_state["owned"], i)
        fs.reset({"Mark as rented": True}, press=["Mark as rented"])
        self._login_as("renter")
        fs.st.session_state["owned"] = i
        run_page("my_listing")
        self.assertEqual(db.get_listing(i)["status"], "rented")

    def test_manage_lockout_after_wrong_codes(self):
        i = db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=900, bed=2, bath=2,
                                price=20000, fair_rent=20000, status="approved",
                                edit_code_hash=listing_logic.hash_code("right")))
        fs.reset()
        for _ in range(6):
            fs.reset({"Listing number": i, "Edit code": "bad"}, press=["Open my listing"], keep_resources=True)
            run_page("my_listing")
        fs.reset({"Listing number": i, "Edit code": "right"}, press=["Open my listing"], keep_resources=True)
        run_page("my_listing")
        self.assertNotIn("owned", fs.st.session_state)   # locked even with the right code

    def _pending(self):
        return db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=900, bed=2, bath=2,
                                   price=20000, fair_rent=20000))

    def _login_as(self, role):
        import auth
        found = auth._find(f"{role}@x.com")
        uid = found["user_id"] if found else auth.create_user("Test Person", f"{role}@x.com", "01712345678", "abcd1234")
        if role == "admin":
            auth.set_role("admin@x.com", "admin")
        auth.login({"user_id": uid, "full_name": "Test Person", "email": f"{role}@x.com",
                    "phone": "01712345678", "role": role, "created_at": ""})

    def test_admin_page_closed_to_visitors(self):
        i = self._pending()
        fs.reset(press=["Approve"])
        run_page("admin")
        self.assertEqual(db.get_listing(i)["status"], "pending")

    def test_admin_page_closed_to_renters(self):
        i = self._pending()
        fs.reset(press=["Approve"])
        self._login_as("renter")
        run_page("admin")
        self.assertEqual(db.get_listing(i)["status"], "pending")

    def test_admin_approve(self):
        i = self._pending()
        fs.reset(press=["Approve"])
        self._login_as("admin")
        run_page("admin")
        self.assertEqual(db.get_listing(i)["status"], "approved")

    def test_admin_rights_can_be_taken_away(self):
        import auth
        i = self._pending()
        fs.reset(press=["Approve"])
        self._login_as("admin")
        auth.set_role("admin@x.com", "renter")   # session still says admin, the database says renter
        run_page("admin")
        self.assertEqual(db.get_listing(i)["status"], "pending")


if __name__ == "__main__":
    unittest.main()
