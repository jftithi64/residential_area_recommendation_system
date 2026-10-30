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
        os.environ["RENT_ADMIN_PASSWORD"] = "secret-pass"
        fs.reset()

    def tearDown(self):
        os.environ.pop("RENT_ADMIN_PASSWORD", None)
        super().tearDown()

    def test_static_pages_run(self):
        for page in ("home", "about", "dashboard"):
            fs.reset()
            run_page(page)

    def test_find_without_search(self):
        run_page("find")

    def test_find_search_with_destination(self):
        fs.reset({"Search university": "Test University", "Type of place": "University"}, press=["Find flats"])
        run_page("find")
        pool = fs.st.session_state["pool"]
        self.assertFalse(pool.empty)
        self.assertTrue((pool.Price <= 25000).all())
        self.assertIn("ranked", fs.st.session_state)
        self.assertTrue(fs.st.session_state["ranked"].km.notna().any())

    def test_find_search_no_destination_and_survey_answer(self):
        fs.reset(press=["Find flats"])
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
        run_page("find")
        self.assertTrue(fs.st.session_state["pool"].empty)

    def test_list_flat_requires_area(self):
        run_page("list_flat")                      # no area chosen: page stops politely

    def test_list_flat_submit_creates_pending_listing(self):
        fs.reset({"Area": "Mirpur", "I agree that the details above are stored and (if ticked) shown, as explained "
                  "on the About and privacy page.": True, "Phone or email (optional)": "017000"},
                 press=["Submit for review"])
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
        run_page("list_flat")
        self.assertEqual(int((db.load_listings().is_extra == 1).sum()), 0)

    def test_manage_listing_flow(self):
        code = listing_logic.make_edit_code()
        i = db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=900, bed=2, bath=2,
                                price=20000, fair_rent=20000, status="approved",
                                edit_code_hash=listing_logic.hash_code(code)))
        fs.reset({"Listing number": i, "Edit code": "wrong"}, press=["Open my listing"])
        run_page("my_listing")
        self.assertNotIn("owned", fs.st.session_state)
        fs.reset({"Listing number": i, "Edit code": code}, press=["Open my listing"])
        run_page("my_listing")
        self.assertEqual(fs.st.session_state["owned"], i)
        fs.reset({"Mark as rented": True}, press=["Mark as rented"])
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

    def test_admin_locked_without_strong_password(self):
        for weak in ("", "admin123", "change-me"):
            os.environ["RENT_ADMIN_PASSWORD"] = weak
            fs.reset()
            run_page("admin")
            self.assertFalse(fs.st.session_state.get("admin_ok"))
        os.environ["RENT_ADMIN_PASSWORD"] = "secret-pass"
        fs.reset({"Admin password": "secret-pass"}, press=["Log in"])
        run_page("admin")
        self.assertTrue(fs.st.session_state.get("admin_ok"))

    def test_admin_wrong_password(self):
        fs.reset({"Admin password": "nope"}, press=["Log in"])
        run_page("admin")
        self.assertFalse(fs.st.session_state.get("admin_ok"))

    def test_admin_approve(self):
        i = db.add_listing(dict(location="Mirpur, Dhaka", place="Mirpur", sub="Unknown", sqft=900, bed=2, bath=2,
                                price=20000, fair_rent=20000))
        fs.reset(press=[f"Approve"])
        fs.st.session_state["admin_ok"] = True
        run_page("admin")
        self.assertEqual(db.get_listing(i)["status"], "approved")


if __name__ == "__main__":
    unittest.main()
