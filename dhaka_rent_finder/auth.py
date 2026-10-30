"""Accounts: sign up, log in, log out.

Stored in the same SQLite file as the listings (table `users`). Passwords are never stored, only a salted
PBKDF2-SHA256 hash. After 5 wrong passwords an account is locked for 15 minutes.

Known limits (be honest about them in your report):
  - Email and phone are NOT verified yet (no OTP / confirmation link). Add an SMS or email OTP before going public.
  - The login lives in Streamlit's session, so a full browser refresh signs the person out.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

import db

DDL = """CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  phone TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT 'renter', password_hash TEXT NOT NULL,
  created_at TEXT, last_login TEXT, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT)"""
COLS = ["user_id", "full_name", "email", "phone", "role", "password_hash", "created_at", "last_login",
        "failed_attempts", "locked_until"]
ROLES = {"renter": "Renter", "owner": "Owner / landlord"}
MAX_FAILS, LOCK_MINUTES, ITERATIONS = 5, 15, 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^01[3-9]\d{8}$")   # Bangladesh mobile: 01XXXXXXXXX


def _connect():
    con = db.connect()
    con.execute(DDL)
    return con


# ------------------------------------------------------------------ passwords
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS).hex()
    return f"{salt}${digest}"


def check_password(password, stored):
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


# ------------------------------------------------------------------ input cleaning
def normalize_phone(raw):
    """'+880 1712-345678' -> '01712345678'."""
    p = re.sub(r"[\s\-()]", "", str(raw or ""))
    if p.startswith("+880"):
        p = "0" + p[4:]
    elif p.startswith("880") and len(p) == 13:
        p = "0" + p[3:]
    return p


def normalize_email(raw):
    return str(raw or "").strip().lower()


def validate_signup(name, email, phone, password, password2, agree):
    """Returns (errors, clean). clean = {'full_name','email','phone'} with tidy values."""
    errors = []
    name = " ".join(str(name or "").split())
    email, phone = normalize_email(email), normalize_phone(phone)
    if len(name) < 2:
        errors.append("Enter your full name.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address, like name@example.com.")
    if not PHONE_RE.match(phone):
        errors.append("Enter a Bangladesh mobile number, like 01712345678.")
    if len(password or "") < 8 or not re.search(r"[A-Za-z]", password or "") or not re.search(r"\d", password or ""):
        errors.append("Password needs at least 8 characters, with letters and numbers.")
    if password != password2:
        errors.append("The two passwords do not match.")
    if not agree:
        errors.append("Tick the box to accept the privacy rules.")
    return errors, {"full_name": name, "email": email, "phone": phone}


# ------------------------------------------------------------------ database
def create_user(full_name, email, phone, password, role="renter"):
    """Insert a user and return the new user_id. Raises ValueError if the email or phone is already used."""
    if role not in ROLES:
        raise ValueError("Unknown role.")
    with _connect() as con:
        taken = con.execute("SELECT email, phone FROM users WHERE email=? OR phone=?", (email, phone)).fetchone()
        if taken:
            what = "email" if taken[0] == email else "mobile number"
            raise ValueError(f"An account with this {what} already exists. Log in instead.")
        cur = con.execute("INSERT INTO users(full_name, email, phone, role, password_hash, created_at) "
                          "VALUES (?,?,?,?,?,?)",
                          (full_name, email, phone, role, hash_password(password),
                           datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid


def _find(identifier):
    ident = str(identifier or "").strip()
    key = normalize_phone(ident) if PHONE_RE.match(normalize_phone(ident)) else normalize_email(ident)
    with _connect() as con:
        row = con.execute("SELECT * FROM users WHERE email=? OR phone=?", (key, key)).fetchone()
    return dict(zip(COLS, row)) if row else None


def authenticate(identifier, password):
    """Returns (user_dict or None, message). The message never says whether the email or the password was wrong."""
    generic = "Wrong email, phone or password."
    user = _find(identifier)
    if user is None:
        hash_password(password or "")   # same work as a real check, so timing does not reveal who has an account
        return None, generic
    now = datetime.now()
    if user["locked_until"] and datetime.fromisoformat(user["locked_until"]) > now:
        mins = int((datetime.fromisoformat(user["locked_until"]) - now).total_seconds() // 60) + 1
        return None, f"Too many wrong attempts. Try again in {mins} minutes."
    if not check_password(password or "", user["password_hash"]):
        fails = int(user["failed_attempts"] or 0) + 1
        lock = (now + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds") if fails >= MAX_FAILS else None
        with _connect() as con:
            con.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE user_id=?",
                        (0 if lock else fails, lock, user["user_id"]))
        return None, generic
    with _connect() as con:
        con.execute("UPDATE users SET failed_attempts=0, locked_until=NULL, last_login=? WHERE user_id=?",
                    (now.isoformat(timespec="seconds"), user["user_id"]))
    return user, ""


# ------------------------------------------------------------------ session (Streamlit)
def _state():
    import streamlit as st
    return st.session_state


def public(user):
    """The part of a user record that is safe to keep in the session."""
    return {k: user[k] for k in ("user_id", "full_name", "email", "phone", "role", "created_at")}


def login(user):
    _state()["user"] = public(user)


def logout():
    _state().pop("user", None)


def current_user():
    return _state().get("user")


def require_login(message="Please log in to use this page."):
    """Call at the top of a page that needs an account. Stops the page for visitors who are not logged in."""
    import streamlit as st
    user = current_user()
    if user is None:
        st.warning(message)
        st.page_link("views/login.py", label="Log in")
        st.page_link("views/signup.py", label="Create an account")
        st.stop()
    return user
