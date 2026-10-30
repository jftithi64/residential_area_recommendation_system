"""Tests for sign-up and log-in. Run: python -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import db


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.tmp.name) / "test.db"
        db._READY = False

    def tearDown(self):
        db.DB_PATH = self.old
        db._READY = False
        self.tmp.cleanup()

    def test_phone_and_email_are_tidied(self):
        self.assertEqual(auth.normalize_phone("+880 1712-345678"), "01712345678")
        self.assertEqual(auth.normalize_email("  Rahim@Example.COM "), "rahim@example.com")

    def test_validation_catches_bad_input(self):
        errors, _ = auth.validate_signup("R", "bad", "123", "short", "different", False)
        self.assertEqual(len(errors), 6)
        errors, clean = auth.validate_signup("Rahim Uddin", "r@x.com", "01712345678", "abcd1234", "abcd1234", True)
        self.assertEqual(errors, [])
        self.assertEqual(clean["phone"], "01712345678")

    def test_signup_then_login_by_email_or_phone(self):
        auth.create_user("Rahim Uddin", "r@x.com", "01712345678", "abcd1234")
        for who in ("r@x.com", "R@X.com", "01712345678", "+8801712345678"):
            user, _ = auth.authenticate(who, "abcd1234")
            self.assertIsNotNone(user, who)

    def test_duplicate_account_is_refused(self):
        auth.create_user("A", "r@x.com", "01712345678", "abcd1234")
        with self.assertRaises(ValueError):
            auth.create_user("B", "r@x.com", "01812345678", "abcd1234")
        with self.assertRaises(ValueError):
            auth.create_user("B", "b@x.com", "01712345678", "abcd1234")

    def test_wrong_password_and_lockout(self):
        auth.create_user("A", "r@x.com", "01712345678", "abcd1234")
        for _ in range(auth.MAX_FAILS):
            user, msg = auth.authenticate("r@x.com", "wrong")
            self.assertIsNone(user)
        user, msg = auth.authenticate("r@x.com", "abcd1234")   # right password, but the account is locked
        self.assertIsNone(user)
        self.assertIn("Too many", msg)

    def test_password_is_not_stored_in_clear(self):
        auth.create_user("A", "r@x.com", "01712345678", "abcd1234")
        with db.connect() as con:
            stored = con.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("abcd1234", stored)
        self.assertTrue(auth.check_password("abcd1234", stored))


if __name__ == "__main__":
    unittest.main()
