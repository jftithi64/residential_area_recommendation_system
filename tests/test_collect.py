"""Tests for collect_data.py (checking and storing real flats). Run: python -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collect_data as cd  # noqa: E402
import common  # noqa: E402

TODAY = date(2026, 10, 27)
GOOD = {"area": "azimpur", "road": "Road 3", "house_no": "12/A", "flat": "4B", "floor": "", "sqft": "900",
        "bed": "2", "bath": "2", "rent_bdt": "18 Thousand", "source_type": "advert",
        "source_url": "https://example.com/ad/1", "date_seen": "2026-10-20", "notes": ""}


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._old = common.COLLECTED_PATH, common.DATA_RAW
        common.COLLECTED_PATH = self.dir / "collected_real.csv"
        common.DATA_RAW = self.dir / "raw.csv"
        pd.DataFrame({"Location": ["Road 1, Mirpur, Dhaka"] * 3, "Area": ["900 sqft"] * 3,
                      "Price": ["20 Thousand", "21 Thousand", "22 Thousand"], "Bed": [2, 2, 2],
                      "Bath": [2, 2, 2]}).to_csv(common.DATA_RAW)

    def tearDown(self):
        common.COLLECTED_PATH, common.DATA_RAW = self._old
        self.tmp.cleanup()

    def row(self, **kw):
        return {**GOOD, **kw}

    def test_good_row_is_cleaned(self):
        row, errs = cd.validate_row(self.row(), TODAY)
        self.assertEqual(errs, [])
        self.assertEqual((row["area"], row["rent_bdt"], row["sqft"]), ("Azimpur", 18000, 900))

    def test_bad_rows_are_refused(self):
        cases = {
            "unknown area": self.row(area="Atlantis"),
            "no road": self.row(road=""),
            "no house": self.row(house_no=""),
            "bad rent": self.row(rent_bdt="12"),
            "mixed up sqft and rent": self.row(sqft="25000", rent_bdt="900"),
            "advert without link": self.row(source_url=""),
            "bad source type": self.row(source_type="rumour"),
            "future date": self.row(date_seen="2026-12-01"),
            "old date": self.row(date_seen="2024-01-01"),
            "phone number": self.row(notes="call 01712-345678"),
            "email": self.row(notes="mail me@x.com"),
            "bed": self.row(bed="2.5"),
        }
        for name, raw in cases.items():
            row, errs = cd.validate_row(raw, TODAY)
            self.assertIsNone(row, name)
            self.assertTrue(errs, name)

    def test_check_and_add_skip_repeats_and_report_lines(self):
        f = self.dir / "in.csv"
        pd.DataFrame([self.row(), self.row(), self.row(house_no="9", rent_bdt="19,500"),
                      self.row(road="")]).to_csv(f, index=False)
        good, problems, repeats = cd.check_file(f, TODAY)
        self.assertEqual((len(good), len(problems), repeats), (2, 1, [3]))
        self.assertEqual(problems[0][0], 5)
        self.assertEqual(cd.add_rows(good), 2)
        good2, _, repeats2 = cd.check_file(f, TODAY)           # same file again: nothing new
        self.assertEqual((len(good2), len(repeats2)), (0, 3))

    def test_collected_rows_join_the_training_data_with_their_address(self):
        cd.add_rows([cd.validate_row(self.row(), TODAY)[0]])
        df = common.load_clean()
        r = df[df.Place == "Azimpur"].iloc[0]
        self.assertEqual(r.Sub, "Road 3")
        self.assertEqual(r.AddressSource, "real_collected")
        self.assertEqual(r.Address, "Flat 4B, House 12/A, Road 3, Azimpur, Dhaka")
        self.assertEqual(r.Floor, 4)
        self.assertEqual(len(df[df.Place == "Mirpur"]), 3)      # the original data is untouched

    def test_status_counts_toward_target(self):
        rows = [cd.validate_row(self.row(house_no=str(n), rent_bdt=str(17000 + n * 100)), TODAY)[0] for n in range(1, 21)]
        cd.add_rows(rows)
        t = cd.status().set_index("area")
        self.assertEqual(t.loc["Azimpur", "status"], "ok")
        self.assertEqual(t.loc["Wari", "status"], "no data")
        self.assertEqual(t.loc["Wari", "still_needed"], 20)


if __name__ == "__main__":
    unittest.main()
