"""Accounts: sign up, log in, log out.

Stored in the same SQLite file as the listings (table `users`). Passwords are never stored, only a salted
PBKDF2-SHA256 hash. After 5 wrong passwords an account is locked for 15 minutes.

Email is verified at sign-up with a 6-digit OTP (hashed, 5-minute expiry, 5 tries, 60-second resend gap),
sent through Gmail SMTP (SMTP_USER / SMTP_PASS in .env). The same code system powers "Forgot password?" on the
Log in page (purpose "reset": separate from the sign-up code, so the two never clash). With no SMTP settings the app runs in DEMO mode and
shows the code on screen instead. The mobile number is NOT verified (real SMS needs a paid gateway).

Admins: ADMIN_EMAIL / ADMIN_PASSWORD in .env create the admin account at start-up (ensure_admin_account). More admins:
`python make_admin.py someone@example.com`. Only accounts with role 'admin' can open the Admin page.

Known limits (be honest about them in your report):
  - Mobile number is not verified.
  - The login lives in Streamlit's session, so a full browser refresh signs the person out.
"""
import hashlib
import hmac
import json
import re
import os
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from pathlib import Path

import db
from common import AREA_COORDS

DDL = """CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  phone TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT 'renter', password_hash TEXT NOT NULL,
  created_at TEXT, last_login TEXT, failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
  email_verified INTEGER NOT NULL DEFAULT 0)"""
OTP_DDL = """CREATE TABLE IF NOT EXISTS email_otps(
  email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  sent_at TEXT NOT NULL)"""
INTEREST_DDL = """CREATE TABLE IF NOT EXISTS user_interests(
  user_id INTEGER PRIMARY KEY, purposes TEXT, areas TEXT, bedrooms INTEGER, budget_max INTEGER, updated_at TEXT)"""
PURPOSES = ["Find a flat to rent", "List my flat for rent", "Check if my rent is fair", "Just looking around"]
COLS = ["user_id", "full_name", "email", "phone", "role", "password_hash", "created_at", "last_login",
        "failed_attempts", "locked_until", "email_verified"]
ROLES = {"renter": "Renter", "owner": "Owner / landlord"}          # what a person can pick when signing up
ADMIN = "admin"                                                      # never selectable at sign-up (see make_admin.py)
ROLE_LABELS = {**ROLES, ADMIN: "Administrator"}
MAX_FAILS, LOCK_MINUTES, ITERATIONS = 5, 15, 200_000
OTP_MINUTES, OTP_TRIES, OTP_RESEND_SECONDS = 5, 5, 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^01[3-9]\d{8}$")   # Bangladesh mobile: 01XXXXXXXXX


def _connect():
    con = db.connect()
    con.execute(DDL)
    con.execute(OTP_DDL)
    con.execute(INTEREST_DDL)
    cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
    if "email_verified" not in cols:   # older database made before OTP existed
        con.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
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
def create_user(full_name, email, phone, password, role="renter", email_verified=False):
    """Insert a user and return the new user_id. Raises ValueError if the email or phone is already used."""
    if role not in ROLES:
        raise ValueError("Unknown role.")
    with _connect() as con:
        taken = con.execute("SELECT email, phone FROM users WHERE email=? OR phone=?", (email, phone)).fetchone()
        if taken:
            what = "email" if taken[0] == email else "mobile number"
            raise ValueError(f"An account with this {what} already exists. Log in instead.")
        cur = con.execute("INSERT INTO users(full_name, email, phone, role, password_hash, created_at, email_verified) "
                          "VALUES (?,?,?,?,?,?,?)",
                          (full_name, email, phone, role, hash_password(password),
                           datetime.now().isoformat(timespec="seconds"), int(bool(email_verified))))
        return cur.lastrowid


# ------------------------------------------------------------------ email OTP
ENV_PATH = Path(__file__).parent / ".env"


def _env(name):
    """Environment variable, falling back to the project's .env file (so `streamlit run` works without VS Code)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name and v.strip():
                return v.strip().strip('"\'')
    except OSError:
        pass
    return ""


def smtp_configured():
    return bool(_env("SMTP_USER") and _env("SMTP_PASS"))


def _hash_code(email, code):
    return hashlib.sha256(f"{email}:{code}".encode()).hexdigest()


def _otp_key(email, purpose="signup"):
    """Row key in email_otps. Sign-up keeps the plain email (old databases keep working); other purposes get a
    prefix, so a password-reset code can never replace or satisfy a sign-up code."""
    return email if purpose == "signup" else f"{purpose}:{email}"


def send_email(to, subject, body):
    """Send through Gmail SMTP (SSL, port 465). Raises on failure."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = _env("SMTP_USER"), to, subject
    msg.set_content(body)
    with smtplib.SMTP_SSL(_env("SMTP_HOST") or "smtp.gmail.com", int(_env("SMTP_PORT") or 465), timeout=20) as s:
        s.login(_env("SMTP_USER"), _env("SMTP_PASS"))
        s.send_message(msg)


def start_email_otp(email, reuse=False, purpose="signup"):
    """Create and send a code. Returns (ok, message, demo_code). demo_code is set only when SMTP is not configured.
    reuse=True: if a code was sent less than a minute ago, do not send another; tell the person to use that one."""
    email = normalize_email(email)
    key = _otp_key(email, purpose)
    demo = not smtp_configured()
    if demo and _env("DEMO_OTP") != "1":   # no silent demo mode: say what is missing
        return False, (f"Email sending is not set up. Add SMTP_USER and SMTP_PASS to {ENV_PATH} (that exact file) "
                       "and restart the site. For testing only, DEMO_OTP=1 shows the code on screen instead."), None
    now = datetime.now()
    with _connect() as con:
        row = con.execute("SELECT sent_at FROM email_otps WHERE email=?", (key,)).fetchone()
        if row and (now - datetime.fromisoformat(row[0])).total_seconds() < OTP_RESEND_SECONDS:
            wait = OTP_RESEND_SECONDS - int((now - datetime.fromisoformat(row[0])).total_seconds())
            if reuse:
                return True, f"A code was sent to {email} a moment ago. Enter it below (or resend in {wait} seconds).", None
            return False, f"Please wait {wait} seconds before asking for a new code.", None
        code = f"{secrets.randbelow(1_000_000):06d}"
        con.execute("INSERT OR REPLACE INTO email_otps(email, code_hash, expires_at, attempts, sent_at) VALUES (?,?,?,0,?)",
                    (key, _hash_code(key, code),
                     (now + timedelta(minutes=OTP_MINUTES)).isoformat(timespec="seconds"),
                     now.isoformat(timespec="seconds")))
    if demo:
        return True, "Demo mode (DEMO_OTP=1): the code is shown below instead of being emailed.", code
    try:
        if purpose == "reset":
            send_email(email, "Reset your Dhaka Rent Finder password",
                       f"Your password reset code is {code}.\nIt works for {OTP_MINUTES} minutes. "
                       "If you did not ask to reset your password, ignore this email: your password has not changed.")
        else:
            send_email(email, "Your Dhaka Rent Finder code",
                       f"Your verification code is {code}.\nIt works for {OTP_MINUTES} minutes. "
                       "If you did not ask for it, ignore this email.")
    except Exception as e:   # wrong App Password, no internet, blocked port...
        return False, f"Could not send the email ({type(e).__name__}). Check SMTP_USER / SMTP_PASS in .env.", None
    return True, f"We sent a 6-digit code to {email}.", None


def check_email_otp(email, code, purpose="signup"):
    """Returns (ok, message). A code works once; 5 wrong tries or 5 minutes kill it."""
    email, code = normalize_email(email), str(code or "").strip()
    key = _otp_key(email, purpose)
    with _connect() as con:
        row = con.execute("SELECT code_hash, expires_at, attempts FROM email_otps WHERE email=?", (key,)).fetchone()
        if not row:
            return False, "No code was sent to this email. Ask for a new one."
        if datetime.fromisoformat(row[1]) < datetime.now():
            con.execute("DELETE FROM email_otps WHERE email=?", (key,))
            return False, "The code has expired. Ask for a new one."
        if row[2] >= OTP_TRIES:
            return False, "Too many wrong tries. Ask for a new code."
        if not hmac.compare_digest(_hash_code(key, code), row[0]):
            con.execute("UPDATE email_otps SET attempts=attempts+1 WHERE email=?", (key,))
            return False, "That code is not right."
        con.execute("DELETE FROM email_otps WHERE email=?", (key,))
    return True, ""


# ------------------------------------------------------------------ forgot password (email OTP)
RESET_SENT = "If an account uses this email, we have sent a 6-digit code to it."   # same text whether or not it exists


def validate_new_password(password, password2):
    """Same password rule as sign-up. Returns a list of error messages (empty = fine)."""
    errors = []
    if len(password or "") < 8 or not re.search(r"[A-Za-z]", password or "") or not re.search(r"\d", password or ""):
        errors.append("Password needs at least 8 characters, with letters and numbers.")
    if password != password2:
        errors.append("The two passwords do not match.")
    return errors


def request_password_reset(email):
    """Step 1 of "Forgot password?". Returns (ok, message, demo_code).
    The message is the same whether or not the email has an account, so nobody can use this form to find out who
    is registered. A code is only created and sent when a normal (non-admin) account has this email. Admin
    passwords come from ADMIN_PASSWORD in .env, so they are not reset here."""
    email = normalize_email(email)
    if not EMAIL_RE.match(email):
        return False, "Enter a valid email address, like name@example.com.", None
    if not smtp_configured() and _env("DEMO_OTP") != "1":   # a setup problem, safe to show to everyone
        return start_email_otp(email, purpose="reset")
    user = _find(email)
    if user is None or user["email"] != email or user["role"] == ADMIN:
        return True, RESET_SENT, None
    ok, msg, demo = start_email_otp(email, reuse=True, purpose="reset")
    if not ok:
        return False, msg, None
    return True, RESET_SENT, demo


def reset_password(email, code, password, password2):
    """Step 2: check the code and save the new password. Returns (ok, message).
    The password is checked BEFORE the code is used up, so a typo in the password does not burn the code."""
    email = normalize_email(email)
    errors = validate_new_password(password, password2)
    if errors:
        return False, " ".join(errors)
    ok, msg = check_email_otp(email, code, purpose="reset")
    if not ok:
        return False, msg
    user = _find(email)
    if user is None or user["role"] == ADMIN:
        return False, "That code is not right."
    with _connect() as con:
        con.execute("UPDATE users SET password_hash=?, failed_attempts=0, locked_until=NULL, email_verified=1 "
                    "WHERE user_id=?", (hash_password(password), user["user_id"]))
    return True, "Your password has been changed. Log in with the new password."


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


WEAK_PASSWORDS = {"admin123", "change-me", "password", "admin", "12345678", "password1"}
_admin_synced = None   # (email, password) already applied in this running process


def ensure_admin_account():
    """Create / refresh the admin account from ADMIN_EMAIL and ADMIN_PASSWORD (environment or .env file).
    Runs when the site starts, so the admin can simply log in on the normal Log in page. The password is stored
    hashed like everyone else's; changing it in .env updates it at the next start. Weak passwords are ignored.
    Returns the admin email, or None when nothing is configured."""
    global _admin_synced
    email, password = normalize_email(_env("ADMIN_EMAIL")), _env("ADMIN_PASSWORD")
    if not email or not password:
        return None
    if (email, password) == _admin_synced:
        return email
    if (not EMAIL_RE.match(email) or password.lower() in WEAK_PASSWORDS or len(password) < 8
            or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password)):
        return None   # refuse a weak or malformed admin login
    with _connect() as con:
        row = con.execute("SELECT user_id, password_hash FROM users WHERE email=?", (email,)).fetchone()
        if row is None:
            con.execute("INSERT INTO users(full_name, email, phone, role, password_hash, created_at, email_verified) "
                        "VALUES (?,?,?,?,?,?,1)",
                        ("Administrator", email, "admin", ADMIN, hash_password(password),
                         datetime.now().isoformat(timespec="seconds")))
        else:
            fields = ["role=?", "email_verified=1"]
            args = [ADMIN]
            if not check_password(password, row[1]):
                fields.append("password_hash=?")
                args.append(hash_password(password))
            con.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id=?", (*args, row[0]))
    _admin_synced = (email, password)
    return email


def is_admin(user=None):
    """True if this person is an admin. Re-reads the role from the database, so removing the role works at once."""
    user = user or current_user()
    if not user:
        return False
    with _connect() as con:
        row = con.execute("SELECT role FROM users WHERE user_id=?", (user["user_id"],)).fetchone()
    return bool(row) and row[0] == ADMIN


def set_role(email, role):
    """Give an existing account a role ('admin', 'owner', 'renter'). Returns True if the account exists."""
    if role not in ROLE_LABELS:
        raise ValueError("Unknown role.")
    with _connect() as con:
        return con.execute("UPDATE users SET role=? WHERE email=?", (role, normalize_email(email))).rowcount > 0


def require_admin():
    """Call at the top of an admin page: visitors and non-admin accounts are stopped."""
    import streamlit as st
    user = require_login("Please log in with your admin account.")
    if not is_admin(user):
        st.error("This page is only for administrators.")
        st.stop()
    return user


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


# ------------------------------------------------------------------ interests (asked, optionally, at sign-up)
def save_interests(user_id, purposes=(), areas=(), bedrooms=None, budget_max=None):
    """Store what the person is interested in. Anything not in the site's lists is dropped; 0 / blank means 'not given'."""
    purposes = [p for p in purposes if p in PURPOSES]
    areas = sorted({a for a in areas if a in AREA_COORDS})
    bedrooms = int(bedrooms) if str(bedrooms or "").isdigit() and 1 <= int(bedrooms) <= 10 else None
    try:
        budget_max = int(budget_max) if budget_max and 3000 <= int(budget_max) <= 500000 else None
    except (TypeError, ValueError):
        budget_max = None
    with _connect() as con:
        con.execute("INSERT OR REPLACE INTO user_interests(user_id, purposes, areas, bedrooms, budget_max, updated_at) "
                    "VALUES (?,?,?,?,?,?)", (int(user_id), json.dumps(purposes), json.dumps(areas), bedrooms, budget_max,
                                             datetime.now().isoformat(timespec="seconds")))


def get_interests(user_id):
    with _connect() as con:
        row = con.execute("SELECT purposes, areas, bedrooms, budget_max FROM user_interests WHERE user_id=?",
                          (int(user_id),)).fetchone()
    if not row:
        return {"purposes": [], "areas": [], "bedrooms": None, "budget_max": None}
    return {"purposes": json.loads(row[0] or "[]"), "areas": json.loads(row[1] or "[]"),
            "bedrooms": row[2], "budget_max": row[3]}
