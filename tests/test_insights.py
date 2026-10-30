"""Tests for sign-up interests and the admin Insights page. Run: python -m unittest discover -s tests -v"""
import runpy
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_streamlit as fs  # noqa: E402

sys.modules["streamlit"] = fs.st

import auth  # noqa: E402
import db  # noqa: E402
import insights  # noqa: E402
from test_core import TempDB  # noqa: E402

TODAY = date(2026, 10, 27)


def run_page(name):
    try:
        runpy.run_path(str(ROOT / "views" / f"{name}.py"), run_name="__page__")
    except (fs.StopPage, fs.RerunPage):
        pass


class InterestTests(TempDB):
    def setUp(self):
        super().setUp()
        self.uid = auth.create_user("Rina", "rina@x.com", "01712345678", "abcd1234")

    def test_save_and_read_back(self):
        auth.save_interests(self.uid, ["Find a flat to rent", "bogus"], ["Wari", "Atlantis"], 2, 25000)
        got = auth.get_interests(self.uid)
        self.assertEqual(got, {"purposes": ["Find a flat to rent"], "areas": ["Wari"], "bedrooms": 2, "budget_max": 25000})

    def test_blank_and_bad_values_become_none(self):
        auth.save_interests(self.uid, [], [], "Any", 0)
        self.assertEqual(auth.get_interests(self.uid)["bedrooms"], None)
        self.assertEqual(auth.get_interests(self.uid)["budget_max"], None)
        auth.save_interests(self.uid, bedrooms=2, budget_max=12)       # budget below the allowed range
        self.assertIsNone(auth.get_interests(self.uid)["budget_max"])
        self.assertEqual(auth.get_interests(9999)["areas"], [])        # person with no interests

    def test_signup_page_stores_interests(self):
        fs.reset(answers={"What brings you here?": ["Check if my rent is fair"],
                          "Full name": "Karim Ali", "Email": "karim@x.com", "Mobile number": "01812345678",
                          "Password": "abcd1234", "Repeat password": "abcd1234",
                          "I agree that my name and contact details are stored to run my account. "
                          "Contact details are shown to others only if I choose that on my listing.": True},
                 press=["Send verification code"])
        import unittest.mock as mock
        with mock.patch.object(auth, "start_email_otp", lambda e, reuse=False: (True, "sent", None)):
            run_page("signup")
        pending = fs.st.session_state["signup_pending"]
        self.assertEqual(pending["interests"]["purposes"], ["Check if my rent is fair"])
        self.assertNotIn("areas", pending["interests"])


class InsightTests(TempDB):
    def setUp(self):
        super().setUp()
        for i, (role, day) in enumerate([("renter", "2026-10-27"), ("renter", "2026-10-27"), ("owner", "2026-10-20"),
                                          ("renter", "2026-08-01")]):
            uid = auth.create_user(f"P{i}", f"p{i}@x.com", f"0171234567{i}", "abcd1234", role=role, email_verified=i < 2)
            with auth._connect() as con:
                con.execute("UPDATE users SET created_at=? WHERE user_id=?", (day + "T10:00:00", uid))
        self.admin = auth.create_user("Boss", "boss@x.com", "01899999999", "abcd1234")
        auth.set_role("boss@x.com", "admin")
        for lid, status, listed in [(1000001, "pending", "2026-10-20"), (1000002, "approved", "2026-10-26"),
                                    (1000003, "rejected", "2026-10-27")]:
            db.add_listing({"location": "Road 1, Wari, Dhaka", "place": "Wari", "sub": "Road 1", "sqft": 800, "bed": 2,
                            "bath": 2, "price": 18000, "fair_rent": 18000, "status": status, "listed_at": listed})

    def test_signup_summary_ignores_admin(self):
        s = insights.signup_summary(TODAY)
        self.assertEqual((s["total"], s["renters"], s["owners"]), (4, 3, 1))
        self.assertEqual((s["last7"], s["last30"], s["verified"]), (2, 3, 2))

    def test_daily_counts_zero_filled(self):
        c = insights.daily_counts(insights.users_df().created_at, 30, TODAY)
        self.assertEqual(len(c), 30)
        self.assertEqual(int(c["count"].iloc[-1]), 2)
        self.assertEqual(int(c["count"].sum()), 3)           # the August sign-up is outside the 30 days
        self.assertEqual(int(insights.daily_counts([], 7, TODAY)["count"].sum()), 0)

    def test_listing_and_review_numbers(self):
        ls, rv = insights.listing_summary(TODAY), insights.review_stats(TODAY)
        self.assertEqual((ls["total"], ls["live"], ls["pending"], ls["rejected"]), (3, 1, 1, 1))
        self.assertEqual((rv["waiting"], rv["oldest_days"], rv["reviewed"], rv["rejected_pct"]), (1, 7, 2, 50))
        self.assertEqual(int(insights.status_counts().loc["pending", "flats"]), 1)

    def test_interest_summary_and_demand(self):
        u = insights.users_df().user_id.tolist()
        auth.save_interests(u[0], ["Find a flat to rent"], ["Wari", "Azimpur"], 2, 18000)
        auth.save_interests(u[1], ["Find a flat to rent", "Just looking around"], ["Azimpur"], 3, 40000)
        it = insights.interest_summary()
        self.assertEqual(it["people"], 2)
        self.assertEqual(int(it["purposes"].loc["Find a flat to rent", "people"]), 2)
        self.assertEqual(int(it["areas"].loc["Azimpur", "people"]), 2)
        dv = insights.demand_vs_supply()
        self.assertEqual(int(dv.loc["Wari", "live owner flats"]), 1)
        self.assertEqual(int(dv.loc["Azimpur", "live owner flats"]), 0)

    def test_empty_database_does_not_break(self):
        with auth._connect() as con:
            con.execute("DELETE FROM users"); con.execute("DELETE FROM listings")
        self.assertEqual(insights.signup_summary(TODAY)["total"], 0)
        self.assertIsNone(insights.review_stats(TODAY)["oldest_days"])
        self.assertEqual(insights.interest_summary()["people"], 0)

    def test_insights_page_runs_for_admin_only(self):
        fs.reset()
        fs.st.session_state["user"] = auth.public(auth._find("boss@x.com"))
        run_page("insights")
        fs.reset()
        fs.st.session_state["user"] = auth.public(auth._find("p0@x.com"))
        with self.assertRaises(fs.StopPage):
            runpy.run_path(str(ROOT / "views" / "insights.py"), run_name="__page__")

    def test_account_page_saves_interests(self):
        fs.reset(answers={"Areas you are interested in": ["Wari"]}, press=["Save interests"])
        fs.st.session_state["user"] = auth.public(auth._find("p0@x.com"))
        run_page("account")
        self.assertEqual(auth.get_interests(auth._find("p0@x.com")["user_id"])["areas"], ["Wari"])


if __name__ == "__main__":
    import unittest
    unittest.main()
