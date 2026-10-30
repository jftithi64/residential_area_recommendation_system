"""Tests for contact links, badges, fair-rent wording and photo handling. Run: python -m unittest discover -s tests -v"""
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import db
import flatcard_logic as fl
import photos


class LogicTests(unittest.TestCase):
    def test_phone_links(self):
        p = fl.phone_links("+880 1712-345678")
        self.assertEqual(p["tel"], "tel:+8801712345678")
        self.assertEqual(p["wa"], "https://wa.me/8801712345678")
        self.assertIsNone(fl.phone_links("call after 5pm"))
        self.assertIsNone(fl.phone_links(None))

    def test_deal_badge(self):
        self.assertEqual(fl.deal_badge(10)[1], "good")
        self.assertEqual(fl.deal_badge(-10)[1], "warn")
        self.assertEqual(fl.deal_badge(40)[1], "warn")
        self.assertEqual(fl.deal_badge(0)[1], "info")
        self.assertIsNone(fl.deal_badge(float("nan")))

    def test_freshness(self):
        self.assertEqual(fl.freshness(0, None, None)[1], "muted")
        self.assertEqual(fl.freshness(float("nan"), None, None)[1], "muted")
        text, kind = fl.freshness(1, float("nan"), "2026-10-14", today="2026-10-17")
        self.assertEqual((text, kind), ("Confirmed 3 days ago", "good"))
        self.assertEqual(fl.freshness(1, "2026-08-01", "2026-08-01", today="2026-10-17")[1], "warn")

    def test_fair_verdict(self):
        self.assertEqual(fl.fair_verdict(10500, 10000, 17)[2], "info")
        self.assertEqual(fl.fair_verdict(7000, 10000, 17)[2], "good")
        self.assertEqual(fl.fair_verdict(13000, 10000, 17)[2], "warn")
        self.assertIn("Much higher", fl.fair_verdict(20000, 10000, 17)[1])


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (db.DB_PATH, photos.PHOTO_DIR)
        db.DB_PATH = Path(self.tmp.name) / "t.db"
        photos.PHOTO_DIR = Path(self.tmp.name) / "photos"
        db._READY = False

    def tearDown(self):
        db.DB_PATH, photos.PHOTO_DIR = self.old
        db._READY = False
        self.tmp.cleanup()

    @staticmethod
    def picture(size=(3000, 2000)):
        buf = io.BytesIO()
        Image.new("RGB", size, (200, 120, 40)).save(buf, "PNG")
        return buf.getvalue()

    def test_photo_is_shrunk_and_stored(self):
        pid = photos.add_photo(1000001, self.picture())
        (got_id, path), = photos.photos_for(1000001)
        self.assertEqual(got_id, pid)
        self.assertLessEqual(max(Image.open(path).size), photos.MAX_SIDE)
        self.assertEqual(photos.first_photos([1000001])[1000001], path)

    def test_not_a_picture_is_refused(self):
        with self.assertRaises(ValueError):
            photos.add_photo(1000001, b"this is not an image")

    def test_limit_and_delete(self):
        for _ in range(photos.MAX_PHOTOS):
            photos.add_photo(1000001, self.picture((300, 200)))
        with self.assertRaises(ValueError):
            photos.add_photo(1000001, self.picture((300, 200)))
        pid, path = photos.photos_for(1000001)[0]
        self.assertFalse(photos.delete_photo(pid, 999))          # wrong listing: nothing deleted
        self.assertTrue(photos.delete_photo(pid, 1000001))
        self.assertFalse(path.exists())
        self.assertEqual(photos.count(1000001), photos.MAX_PHOTOS - 1)


if __name__ == "__main__":
    unittest.main()
