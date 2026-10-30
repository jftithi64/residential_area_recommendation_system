"""Unit tests for the pure logic and the database layer. Run from the project folder:

    python -m unittest discover -s tests -v

They use a temporary database and never touch data/rent.db or the internet.
"""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402
import coverage  # noqa: E402
import db  # noqa: E402
import listing_logic as ll  # noqa: E402
import nearby  # noqa: E402
import recommender  # noqa: E402

PLACES = ["Mirpur", "Uttara", "Dhanmondi"]


class TempDB(unittest.TestCase):
    """Each test gets its own empty database file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "rent.db"
        db._READY = False

    def tearDown(self):
        db.DB_PATH = self._old
        db._READY = False
        self._tmp.cleanup()

    def add_base(self, listing_id, place, price=20000, sqft=800, bed=2, bath=2, **kw):
        with db.connect() as con:
            con.execute("INSERT INTO listings(listing_id, location, place, sub, sqft, bed, bath, price, fair_rent, "
                        "dup_count, is_extra, status, entry_kind) VALUES (?,?,?,?,?,?,?,?,?,1,0,'approved','available')",
                        (listing_id, f"Block A, {place}, Dhaka", place, "Block A", sqft, bed, bath, price,
                         kw.get("fair_rent", price)))


class TestParsing(unittest.TestCase):
    def test_price(self):
        self.assertEqual(common.parse_price("20 Thousand"), 20000)
        self.assertEqual(common.parse_price("1.2 Lakh"), 120000)
        self.assertEqual(common.parse_price("1,5 Thousand".replace(",", "")), 15000)
        self.assertTrue(np.isnan(common.parse_price("negotiable")))

    def test_sqft(self):
        self.assertEqual(common.parse_sqft("1,200 sqft"), 1200)
        self.assertTrue(np.isnan(common.parse_sqft("n/a")))

    def test_split_location(self):
        self.assertEqual(common.split_location("Block H, Bashundhara R-A, Dhaka"), ("Bashundhara R-A", "Block H"))
        self.assertEqual(common.split_location("Mirpur, Dhaka"), ("Mirpur", "Unknown"))
        p, s = common.split_location("")
        self.assertTrue(pd.isna(p) and pd.isna(s))

    def test_haversine(self):
        self.assertAlmostEqual(float(common.haversine_km((23.8, 90.4), (23.8, 90.4))), 0, places=6)
        d = float(common.haversine_km((23.8069, 90.3687), (23.8759, 90.3795)))  # Mirpur -> Uttara
        self.assertTrue(6 < d < 10)

    def test_stable_ids(self):
        df = pd.DataFrame({"a": [f"loc{i}" for i in range(5000)], "b": range(5000)})
        ids = common.stable_ids(df, ["a", "b"])
        self.assertEqual(ids, common.stable_ids(df, ["a", "b"]))          # same input, same ids
        self.assertEqual(len(set(ids)), 5000)                             # unique
        self.assertTrue(all(1 <= i < db.BASE_ID for i in ids))            # never clash with user-added ids
        self.assertEqual(ids[:10], common.stable_ids(df.iloc[:10], ["a", "b"]))  # not tied to row position


class TestValidate(unittest.TestCase):
    def check(self, **kw):
        a = dict(place="Mirpur", sqft=900, bed=2, bath=2, price=20000, known_places=PLACES, fair_rent=None)
        a.update(kw)
        return ll.validate(**a)

    def test_happy_path(self):
        self.assertEqual(self.check(), ([], []))

    def test_unknown_area(self):
        errors, _ = self.check(place="Atlantis")
        self.assertTrue(any("area" in e for e in errors))

    def test_size_limits(self):
        for sqft in (100, 9000):
            self.assertTrue(self.check(sqft=sqft)[0])

    def test_no_meaningful_minimum_rent(self):
        errors, _ = self.check(price=1500, sqft=600, bed=1, bath=1)
        self.assertEqual(errors, [])
        self.assertTrue(self.check(price=500)[0])    # still catches typing errors

    def test_rooms(self):
        self.assertTrue(self.check(bed=0)[0])
        self.assertTrue(self.check(bath=0)[0])
        self.assertTrue(self.check(bed=11)[0])

    def test_price_per_sqft_range(self):
        self.assertTrue(self.check(price=400000, sqft=300)[0])   # ~1333 per sqft

    def test_far_from_fair_is_flagged_not_rejected(self):
        errors, flags = self.check(price=40000, fair_rent=20000)
        self.assertEqual(errors, [])
        self.assertEqual(len(flags), 1)
        self.assertIn("above", flags[0])
        _, flags = self.check(price=10000, fair_rent=20000)
        self.assertIn("below", flags[0])

    def test_near_fair_not_flagged(self):
        self.assertEqual(self.check(price=22000, fair_rent=20000)[1], [])

    def test_tiny_bedrooms_flagged(self):
        _, flags = self.check(sqft=250, bed=4, bath=1, price=9000)
        self.assertTrue(any("per bedroom" in f for f in flags))

    def test_errors_skip_later_checks(self):
        errors, flags = self.check(place="Atlantis", price=99999, fair_rent=20000)
        self.assertTrue(errors)
        self.assertEqual(flags, [])


class TestEditCode(unittest.TestCase):
    def test_roundtrip_and_salt(self):
        code = ll.make_edit_code()
        h1, h2 = ll.hash_code(code), ll.hash_code(code)
        self.assertNotEqual(h1, h2)                        # salted
        self.assertTrue(ll.check_code(code, h1))
        self.assertTrue(ll.check_code(f"  {code} ", h1))   # copy-paste whitespace is fine
        self.assertFalse(ll.check_code("wrong", h1))

    def test_code_is_long_enough(self):
        self.assertGreaterEqual(len(ll.make_edit_code()), 13)

    def test_empty_inputs(self):
        self.assertFalse(ll.check_code("x", None))
        self.assertFalse(ll.check_code("x", ""))
        self.assertFalse(ll.check_code(None, ll.hash_code("x")))

    def test_legacy_sha256_hash_still_works(self):
        import hashlib
        legacy = hashlib.sha256(b"oldcode").hexdigest()
        self.assertTrue(ll.check_code("oldcode", legacy))
        self.assertFalse(ll.check_code("nope", legacy))


class TestText(unittest.TestCase):
    def test_facility_text(self):
        r = {"tenant_rule": "family", "floor": 3.0, "lift": 1, "gas": 0, "parking": float("nan"),
             "available_from": "2026-11-01"}
        self.assertEqual(ll.facility_text(r), "Family only, floor 3, lift, available from 2026-11-01")
        self.assertEqual(ll.facility_text({}), "")
        self.assertEqual(ll.facility_text({"tenant_rule": "any"}), "")

    def test_address_label(self):
        self.assertEqual(ll.address_label("Flat 1", "synthetic_demo"), "Flat 1 [demo address]")
        self.assertEqual(ll.address_label("Flat 1", "user"), "Flat 1")
        self.assertEqual(ll.address_label(None, "user"), "")
        self.assertEqual(ll.address_label("  ", "user"), "")


class TestBaselineScore(unittest.TestCase):
    def feats(self, **kw):
        base = dict(deal_gap=0.0, size_gap=0.0, price_ratio=0.5, km=2.0)
        base.update(kw)
        return pd.DataFrame([base])

    def test_range_0_to_100(self):
        for f in (self.feats(deal_gap=5, size_gap=5, price_ratio=9, km=99),
                  self.feats(deal_gap=-5, size_gap=-1, price_ratio=-1, km=-3)):
            s = float(recommender.baseline_from_features(f, cap=10).iloc[0])
            self.assertTrue(0 <= s <= 100)

    def test_cheaper_than_fair_scores_higher(self):
        good = recommender.baseline_from_features(self.feats(deal_gap=0.2), cap=10).iloc[0]
        bad = recommender.baseline_from_features(self.feats(deal_gap=-0.2), cap=10).iloc[0]
        self.assertGreater(good, bad)

    def test_closer_scores_higher_only_when_commute_used(self):
        near, far = self.feats(km=1), self.feats(km=9)
        self.assertGreater(recommender.baseline_from_features(near, cap=10).iloc[0],
                           recommender.baseline_from_features(far, cap=10).iloc[0])
        self.assertAlmostEqual(recommender.baseline_from_features(near, cap=10, use_commute=False).iloc[0],
                               recommender.baseline_from_features(far, cap=10, use_commute=False).iloc[0])

    def test_all_weights_zero_does_not_divide_by_zero(self):
        w = {"w_value": 0, "w_space": 0, "w_commute": 0, "w_savings": 0}
        s = recommender.baseline_from_features(self.feats(), cap=10, weights=w)
        self.assertTrue(np.isfinite(s.iloc[0]))

    def test_deal_gap_is_capped(self):
        a = recommender.baseline_from_features(self.feats(deal_gap=0.3), cap=10).iloc[0]
        b = recommender.baseline_from_features(self.feats(deal_gap=0.9), cap=10).iloc[0]
        self.assertAlmostEqual(a, b)   # beyond +30% is more likely missing info than a real bargain


class TestDatabase(TempDB):
    def rec(self, **kw):
        r = dict(location="Block A, Mirpur, Dhaka", place="Mirpur", sub="Block A", sqft=900, bed=2, bath=2,
                 price=20000, fair_rent=21000)
        r.update(kw)
        return r

    def test_user_ids_start_at_base_and_increase(self):
        a, b = db.add_listing(self.rec()), db.add_listing(self.rec(price=30000))
        self.assertEqual(a, db.BASE_ID)
        self.assertEqual(b, db.BASE_ID + 1)

    def test_new_listing_defaults(self):
        i = db.add_listing(self.rec(address="Road 5"))
        row = db.get_listing(i)
        self.assertEqual((row["status"], row["is_extra"], row["entry_kind"]), ("pending", 1, "available"))
        self.assertEqual(row["address_source"], "user")

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            db.add_listing(self.rec(nonsense=1))
        i = db.add_listing(self.rec())
        with self.assertRaises(ValueError):
            db.update_listing(i, bogus=1)
        with self.assertRaises(ValueError):
            db.update_listing(i)

    def test_status_flow_and_validation(self):
        i = db.add_listing(self.rec())
        db.set_status(i, "approved")
        self.assertEqual(db.get_listing(i)["status"], "approved")
        with self.assertRaises(ValueError):
            db.set_status(i, "teleported")

    def test_private_columns_hidden_by_default(self):
        db.add_listing(self.rec(contact="017xxxxxxxx", edit_code_hash="h"))
        self.assertNotIn("contact", db.load_listings().columns)
        self.assertIn("contact", db.load_listings(include_private=True).columns)

    def test_public_contacts_only_when_approved_and_public(self):
        a = db.add_listing(self.rec(contact="111", contact_public=1, status="approved"))
        b = db.add_listing(self.rec(contact="222", contact_public=0, status="approved"))
        c = db.add_listing(self.rec(contact="333", contact_public=1, status="pending"))
        self.assertEqual(db.public_contacts([a, b, c]), {a: "111"})
        self.assertEqual(db.public_contacts([]), {})

    def test_find_duplicate(self):
        i = db.add_listing(self.rec())
        args = ("Mirpur", "Block A", 910, 2, 2, 20500)
        self.assertEqual(db.find_duplicate(*args), i)                                  # within 3% / 5%
        self.assertIsNone(db.find_duplicate("Mirpur", "Block A", 1200, 2, 2, 20500))   # size too different
        self.assertIsNone(db.find_duplicate("Mirpur", "Block A", 910, 2, 2, 30000))    # rent too different
        db.set_status(i, "rejected")
        self.assertIsNone(db.find_duplicate(*args))                                    # rejected ones do not count

    def test_connections_are_closed(self):
        import sqlite3
        with db.connect() as con:
            pass
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")

    def test_coord_key_prefers_block_then_area(self):
        coords = {("Mirpur", ""): (1, 1, "m"), ("Mirpur", "Block A"): (2, 2, "osm")}
        self.assertEqual(db.coord_key(coords, "Mirpur", "Block A"), ("Mirpur", "Block A"))
        self.assertEqual(db.coord_key(coords, "Mirpur", "Block Z"), ("Mirpur", ""))
        self.assertIsNone(db.coord_key(coords, "Nowhere", "x"))

    def test_route_cache_roundtrip(self):
        db.save_routes(23.81234567, 90.41234567, [("Mirpur", "Block A", 4.2, 15.0, "osrm")])
        got = db.cached_routes(23.81234567, 90.41234567, "osrm")
        self.assertEqual(got[("Mirpur", "Block A")][:2], (4.2, 15.0))
        self.assertEqual(db.cached_routes(23.81234567, 90.41234567, "google"), {})


class TestPrepare(TempDB):
    def test_filters_and_budget(self):
        self.add_base(1, "Mirpur", price=15000)
        self.add_base(2, "Mirpur", price=25000)
        out = recommender.prepare(20000, target_sqft=800)
        self.assertEqual(list(out.listing_id), [1])

    def test_no_minimum_rent_by_default(self):
        self.add_base(1, "Mirpur", price=1200, sqft=300, bed=1, bath=1)
        out = recommender.prepare(20000, target_sqft=300)
        self.assertEqual(list(out.listing_id), [1])

    def test_inactive_listings_never_recommended(self):
        self.add_base(1, "Mirpur")
        self.add_base(2, "Mirpur")
        db.update_listing(2, status="rented")
        self.assertEqual(list(recommender.prepare(30000, target_sqft=800).listing_id), [1])

    def test_unknown_distance_is_not_treated_as_closest(self):
        self.add_base(1, "Mirpur")
        self.add_base(2, "Narnia")          # no coordinates anywhere
        dest = {"name": "Uttara school", "lat": 23.8759, "lon": 90.3795}
        out = recommender.prepare(30000, target_sqft=800, destination=dest, use_network=False).set_index("listing_id")
        self.assertTrue(np.isnan(out.at[2, "km"]))                       # shown as unknown, not as 0 km
        self.assertGreater(out.at[1, "f_km"], 0)
        self.assertGreaterEqual(out.at[2, "f_km"], out.at[1, "f_km"])    # scored as the farthest, never the closest

    def test_offline_distance_is_labelled_estimate(self):
        self.add_base(1, "Mirpur")
        dest = {"name": "x", "lat": 23.8759, "lon": 90.3795}
        out = recommender.prepare(30000, target_sqft=800, destination=dest, use_network=False)
        self.assertEqual(out.dist_source.iloc[0], "estimate")

    def test_max_km_drops_far_flats(self):
        self.add_base(1, "Mirpur")
        self.add_base(2, "Uttara")
        dest = {"name": "x", "lat": 23.8759, "lon": 90.3795}   # Uttara
        out = recommender.prepare(30000, target_sqft=800, destination=dest, max_km=3, use_network=False)
        self.assertEqual(list(out.listing_id), [2])

    def test_walking_distance_costs_nothing(self):
        self.add_base(1, "Uttara")
        dest = {"name": "x", "lat": 23.8759, "lon": 90.3795}
        out = recommender.prepare(30000, target_sqft=800, destination=dest, use_network=False)
        self.assertEqual(out.travel_cost.iloc[0], 0)
        self.assertEqual(out.total_monthly.iloc[0], out.Price.iloc[0])

    def test_tenant_filter(self):
        self.add_base(1, "Mirpur")
        self.add_base(2, "Mirpur")
        self.add_base(3, "Mirpur")
        db.update_listing(2, tenant_rule="family")
        db.update_listing(3, tenant_rule="bachelor_male")
        lenient = recommender.prepare(30000, target_sqft=800, tenant="family")
        strict = recommender.prepare(30000, target_sqft=800, tenant="family", strict_tenant=True)
        self.assertEqual(sorted(lenient.listing_id), [1, 2])   # unknown rule stays
        self.assertEqual(sorted(strict.listing_id), [2])

    def test_empty_result_is_safe(self):
        self.add_base(1, "Mirpur", price=50000)
        self.assertTrue(recommender.prepare(1000, target_sqft=800).empty)
        self.assertTrue(recommender.rank(recommender.prepare(1000, target_sqft=800)).empty)


class TestRank(TempDB):
    def test_better_deal_ranks_first_and_block_cap(self):
        for i, price in enumerate([14000, 18000, 19000, 19500], start=1):
            self.add_base(i, "Mirpur", price=price, fair_rent=20000)
        pool = recommender.prepare(20000, target_sqft=800)
        out = recommender.rank(pool, use_ranker=False, max_per_block=3, w_commute=0)
        self.assertEqual(out.iloc[0].listing_id, 1)
        self.assertEqual(len(out), 3)                       # at most 3 per block
        self.assertTrue(out.score.is_monotonic_decreasing)
        self.assertTrue(out.why.str.len().gt(0).all())


class TestCoverage(unittest.TestCase):
    def frame(self):
        cols = ["listing_id", "Place", "Price", "is_extra", "status", "entry_kind", "listed_at", "updated_at",
                "floor", "lift", "gas", "tenant_rule"]
        rows = [
            (1, "Mirpur", 15000, 0, "approved", "available", None, None, None, None, None, None),
            (2, "Mirpur", 16000, 0, "approved", "available", None, None, None, None, None, None),
            (3, "Uttara", 30000, 0, "approved", "available", None, None, None, None, None, None),
            (4, "Uttara", 32000, 1, "approved", "available", "2026-09-01", "2026-09-01", 3, 1, 1, "family"),
            (5, "Uttara", 31000, 1, "pending", "available", "2026-10-01", None, None, None, None, None),
        ]
        return pd.DataFrame(rows, columns=cols)

    def test_table(self):
        t = coverage.coverage_table(self.frame(), today="2026-10-08").set_index("Area")
        self.assertEqual(t.at["Mirpur", "Status"], "Needs data")
        self.assertEqual(t.at["Uttara", "User-listed (live)"], 1)
        self.assertEqual(t.at["Uttara", "Waiting for review"], 1)
        self.assertEqual(t.at["Uttara", "Days since newest"], 37)
        self.assertEqual(t.at["Uttara", "Missing details (%)"], 0)

    def test_stale_area(self):
        t = coverage.coverage_table(self.frame(), today="2026-12-01").set_index("Area")
        self.assertEqual(t.at["Uttara", "Status"], "Stale")

    def test_sorted_by_priority(self):
        t = coverage.coverage_table(self.frame(), today="2026-10-08")
        self.assertTrue(t.Priority.is_monotonic_decreasing)

    def test_summary(self):
        s = coverage.summary(self.frame(), today="2026-10-08")
        self.assertEqual((s["live_total"], s["original"], s["user_live"], s["pending"]), (4, 3, 1, 1))
        self.assertEqual(s["added_30d"], 0)
        self.assertEqual(s["added_7d"], 0)
        self.assertEqual(s["areas"], 2)


class TestNearby(TempDB):
    def setUp(self):
        super().setUp()
        with db.connect() as con:
            con.executemany("INSERT INTO location_coords VALUES (?,?,?,?,?)",
                            [("Mirpur", "", 23.8069, 90.3687, "m"), ("Kafrul", "", 23.7960, 90.3830, "m"),
                             ("Uttara", "", 23.8759, 90.3795, "m"), ("Dhanmondi", "", 23.7461, 90.3742, "m")])
            con.executemany("INSERT INTO landmarks(name, kind, area, lat, lon, coord_source) VALUES (?,?,?,?,?,?)",
                            [("Near School", "school", "Mirpur", 23.8100, 90.3700, "osm"),
                             ("Far University", "university", "Uttara", 23.8759, 90.3795, "osm"),
                             ("Mirpur Office", "office", "Mirpur", 23.8000, 90.3600, "osm"),
                             ("No Coords", "school", "Mirpur", None, None, "manual")])

    def test_areas_sorted_nearest_first_and_exclude_self(self):
        out = nearby.nearby_areas("Mirpur", k=3, max_km=50)
        names = [a["area"] for a in out]
        self.assertNotIn("Mirpur", names)
        self.assertEqual(names[0], "Kafrul")
        self.assertEqual([a["km"] for a in out], sorted(a["km"] for a in out))

    def test_area_limit_and_unknown(self):
        self.assertEqual(len(nearby.nearby_areas("Mirpur", k=1, max_km=50)), 1)
        self.assertEqual(nearby.nearby_areas("Atlantis"), [])
        self.assertEqual(nearby.nearby_areas("Mirpur", max_km=0.1), [])

    def test_landmarks_nearest_first_filter_and_skip_missing_coords(self):
        out = nearby.nearby_landmarks("Mirpur", max_km=50)
        names = [x["name"] for x in out]
        self.assertNotIn("No Coords", names)
        self.assertEqual(names[0], "Near School")
        only = nearby.nearby_landmarks("Mirpur", kinds=["office"], max_km=50)
        self.assertEqual([x["name"] for x in only], ["Mirpur Office"])
        self.assertEqual(nearby.nearby_landmarks("Mirpur", max_km=0.01), [])

    def test_exact_position_overrides_area_centre(self):
        out = nearby.nearby_landmarks("Mirpur", exact=(23.8759, 90.3795), kinds=["university"], max_km=1)
        self.assertEqual([x["name"] for x in out], ["Far University"])

    def test_offline_road_distance_is_labelled_estimate(self):
        km, mn, src = nearby.road_distance("Mirpur", "", 23.8759, 90.3795, use_network=False)
        self.assertEqual(src, "estimate")
        self.assertGreater(km, 0)

    def test_unknown_place_has_no_distance(self):
        self.assertIsNone(nearby.road_distance("Atlantis", "x", 23.8, 90.4, use_network=False))


if __name__ == "__main__":
    unittest.main()
