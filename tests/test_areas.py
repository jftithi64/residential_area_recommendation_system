"""Extra Dhaka areas and the rent estimate for areas with no data. Run: python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common  # noqa: E402
import listing_logic  # noqa: E402
import recommender  # noqa: E402

KNOWN = {"Sutrapur", "Motijheel", "Bangshal", "Mirpur"}


class AreaTests(unittest.TestCase):
    def test_extra_areas_are_in_the_area_list(self):
        names = listing_logic.area_names()
        for a in ("Wari", "Pallabi", "Gulistan", "Demra", "Farmgate"):
            self.assertIn(a, names)
        self.assertGreater(len(names), 100)

    def test_coordinates_are_inside_dhaka(self):
        for name, (la, lo) in common.AREA_COORDS.items():
            self.assertTrue(23.65 < la < 23.92 and 90.32 < lo < 90.52, name)

    def test_unknown_area_uses_nearest_known_areas(self):
        with mock.patch.object(recommender, "known_areas", lambda: KNOWN):
            prox = recommender.proxy_areas("Wari")
            self.assertEqual(len(prox), 3)
            self.assertEqual(prox[0][0], "Sutrapur")           # nearest first
            self.assertEqual(recommender.proxy_areas("Motijheel"), [])   # trained area: no proxy
            vals = {"Sutrapur": 10000.0, "Bangshal": 20000.0, "Motijheel": 30000.0}
            with mock.patch.object(recommender, "_predict_known", lambda a, *x: vals[a]):
                est = recommender.predict_fair_rent("Wari", "", 1000, 2, 2)
            self.assertTrue(10000 < est < 30000)
            self.assertLess(est, 20000)                         # nearer areas count for more


if __name__ == "__main__":
    unittest.main()
