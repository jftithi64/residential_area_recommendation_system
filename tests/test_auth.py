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
        self._orig_env = auth._env

    def tearDown(self):
        auth._env = self._orig_env   # some tests replace it; do not leak into other test files
        auth._admin_synced = None
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

    def test_email_otp_flow(self):
        auth._env = lambda name: "1" if name == "DEMO_OTP" else ""   # no SMTP, demo mode on: the code is returned
        ok, _, code = auth.start_email_otp("R@X.com")
        self.assertTrue(ok)
        self.assertEqual(len(code), 6)
        ok, _, _ = auth.start_email_otp("r@x.com")   # resend too soon
        self.assertFalse(ok)
        self.assertFalse(auth.check_email_otp("r@x.com", "000000" if code != "000000" else "111111")[0])
        self.assertTrue(auth.check_email_otp("r@x.com", code)[0])
        self.assertFalse(auth.check_email_otp("r@x.com", code)[0])   # a code works once

    def test_email_otp_locks_after_too_many_tries(self):
        auth._env = lambda name: "1" if name == "DEMO_OTP" else ""
        _, _, code = auth.start_email_otp("r@x.com")
        wrong = "111111" if code != "111111" else "222222"
        for _ in range(auth.OTP_TRIES):
            auth.check_email_otp("r@x.com", wrong)
        self.assertFalse(auth.check_email_otp("r@x.com", code)[0])

    def test_otp_refused_when_email_is_not_set_up(self):
        auth._env = lambda name: ""
        ok, msg, code = auth.start_email_otp("r@x.com")
        self.assertFalse(ok)
        self.assertIn("SMTP_USER", msg)
        self.assertIsNone(code)

    def _env_with(self, **kw):
        auth._env = lambda name: kw.get(name, "")
        auth._admin_synced = None

    def test_admin_account_comes_from_env(self):
        self._env_with(ADMIN_EMAIL="Boss@X.com", ADMIN_PASSWORD="Strong1pass")
        self.assertEqual(auth.ensure_admin_account(), "boss@x.com")
        user, _ = auth.authenticate("boss@x.com", "Strong1pass")
        self.assertIsNotNone(user)
        self.assertTrue(auth.is_admin(user))
        self.assertEqual(auth.ensure_admin_account(), "boss@x.com")   # second call changes nothing
        with db.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)

    def test_admin_password_change_and_weak_password(self):
        self._env_with(ADMIN_EMAIL="boss@x.com", ADMIN_PASSWORD="Strong1pass")
        auth.ensure_admin_account()
        self._env_with(ADMIN_EMAIL="boss@x.com", ADMIN_PASSWORD="Another2pass")
        auth.ensure_admin_account()
        self.assertIsNone(auth.authenticate("boss@x.com", "Strong1pass")[0])
        self.assertIsNotNone(auth.authenticate("boss@x.com", "Another2pass")[0])
        self._env_with(ADMIN_EMAIL="weak@x.com", ADMIN_PASSWORD="admin123")
        self.assertIsNone(auth.ensure_admin_account())
        self.assertIsNone(auth._find("weak@x.com"))

    def test_existing_account_with_admin_email_becomes_admin(self):
        uid = auth.create_user("Me", "boss@x.com", "01712345678", "abcd1234")
        self._env_with(ADMIN_EMAIL="boss@x.com", ADMIN_PASSWORD="Strong1pass")
        auth.ensure_admin_account()
        self.assertTrue(auth.is_admin({"user_id": uid}))

    def test_password_is_not_stored_in_clear(self):
        auth.create_user("A", "r@x.com", "01712345678", "abcd1234")
        with db.connect() as con:
            stored = con.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("abcd1234", stored)
        self.assertTrue(auth.check_password("abcd1234", stored))

    # ---------------------------------------------------------- forgot password
    def _demo_env(self):
        auth._env = lambda name: "1" if name == "DEMO_OTP" else ""

    def test_reset_password_with_otp(self):
        self._demo_env()
        auth.create_user("A", "r@x.com", "01712345678", "oldpass123")
        ok, msg, code = auth.request_password_reset("R@X.com")
        self.assertTrue(ok)
        self.assertEqual(len(code), 6)
        # wrong code, mismatched or weak password: nothing changes, and a weak password does not burn the code
        self.assertFalse(auth.reset_password("r@x.com", "000000" if code != "000000" else "111111", "newpass123", "newpass123")[0])
        self.assertFalse(auth.reset_password("r@x.com", code, "short", "short")[0])
        self.assertFalse(auth.reset_password("r@x.com", code, "newpass123", "different1")[0])
        ok, _ = auth.reset_password("r@x.com", code, "newpass123", "newpass123")
        self.assertTrue(ok)
        self.assertIsNone(auth.authenticate("r@x.com", "oldpass123")[0])
        self.assertIsNotNone(auth.authenticate("r@x.com", "newpass123")[0])
        self.assertFalse(auth.reset_password("r@x.com", code, "another123", "another123")[0])   # a code works once

    def test_reset_does_not_reveal_whether_an_account_exists(self):
        self._demo_env()
        auth.create_user("A", "r@x.com", "01712345678", "oldpass123")
        known = auth.request_password_reset("r@x.com")
        unknown = auth.request_password_reset("nobody@x.com")
        self.assertEqual(known[:2], unknown[:2])        # same ok flag, same message
        self.assertIsNone(unknown[2])                   # but no code was made for the stranger
        self.assertFalse(auth.reset_password("nobody@x.com", "123456", "newpass123", "newpass123")[0])

    def test_reset_code_and_signup_code_do_not_clash(self):
        self._demo_env()
        auth.create_user("A", "r@x.com", "01712345678", "oldpass123")
        _, _, signup_code = auth.start_email_otp("r@x.com")
        _, _, reset_code = auth.request_password_reset("r@x.com")
        self.assertTrue(auth.check_email_otp("r@x.com", signup_code)[0])
        self.assertTrue(auth.reset_password("r@x.com", reset_code, "newpass123", "newpass123")[0])

    def test_reset_unlocks_a_locked_account(self):
        self._demo_env()
        auth.create_user("A", "r@x.com", "01712345678", "oldpass123")
        for _ in range(auth.MAX_FAILS):
            auth.authenticate("r@x.com", "wrong")
        _, _, code = auth.request_password_reset("r@x.com")
        self.assertTrue(auth.reset_password("r@x.com", code, "newpass123", "newpass123")[0])
        self.assertIsNotNone(auth.authenticate("r@x.com", "newpass123")[0])

    def test_admin_password_is_not_reset_by_email(self):
        self._env_with(ADMIN_EMAIL="boss@x.com", ADMIN_PASSWORD="Strong1pass", DEMO_OTP="1")
        auth.ensure_admin_account()
        ok, _, code = auth.request_password_reset("boss@x.com")
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_reset_too_many_wrong_tries(self):
        self._demo_env()
        auth.create_user("A", "r@x.com", "01712345678", "oldpass123")
        _, _, code = auth.request_password_reset("r@x.com")
        wrong = "111111" if code != "111111" else "222222"
        for _ in range(auth.OTP_TRIES):
            auth.reset_password("r@x.com", wrong, "newpass123", "newpass123")
        self.assertFalse(auth.reset_password("r@x.com", code, "newpass123", "newpass123")[0])

    def test_reset_needs_email_setup(self):
        auth._env = lambda name: ""
        ok, msg, _ = auth.request_password_reset("r@x.com")
        self.assertFalse(ok)
        self.assertIn("SMTP_USER", msg)


if __name__ == "__main__":
    unittest.main()
