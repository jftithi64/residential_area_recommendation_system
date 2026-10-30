"""Role-wise menu rights: which pages a renter and an owner can see.

The admin sets them on the "Menu rights" page (views/menu_rights.py). They are stored in the same SQLite file
(table `role_permissions`, one row per role + page, 1 = allowed, 0 = hidden).

Rules
  - Admins always see every page. Their rights cannot be changed here.
  - A page with no saved row follows its default: everything is allowed for renters and owners.
  - "Locked" pages (Home, About, My account) are always shown to logged-in people, so nobody can lose the way
    home or the log-out button.
  - Visitors (not logged in) see ONLY Home, plus Log in and Sign up. This is fixed: searching, listing, the
    dashboard and every other page need an account. A visitor who reaches such a page another way gets a
    "Log in or sign up" prompt from guard(). For logged-in renters and owners a switched-off page is hidden.
  - Hiding a page removes it from the menu AND blocks it: guard() stops the page if somebody reaches it
    another way (a saved link, a button on another page).
"""
import db

DDL = """CREATE TABLE IF NOT EXISTS role_permissions(
  role TEXT NOT NULL, page_key TEXT NOT NULL, allowed INTEGER NOT NULL,
  updated_at TEXT, updated_by TEXT, PRIMARY KEY(role, page_key))"""

# key -> (file, title, icon, locked). `locked` pages cannot be switched off.
PAGES = {
    "home": ("views/start.py", "Home", "🏠", True),
    "browse": ("views/browse.py", "Browse flats", "🔎", False),
    "fair_rent": ("views/fair_rent.py", "Is my rent fair?", "⚖️", False),
    "list_flat": ("views/list_flat.py", "List a flat", "➕", False),
    "add_photos": ("views/add_photos.py", "Add photos", "📷", False),
    "my_listing": ("views/my_listing.py", "Manage my listing", "✏️", False),
    "find": ("views/find.py", "Advanced search", "🧭", False),
    "dashboard": ("views/dashboard.py", "Dashboard", "📊", False),
    "about": ("views/about.py", "About and privacy", "ℹ️", True),
    "account": ("views/account.py", "My account", "👤", True),
}
# Pages only an administrator can open. They are not switchable (the pages themselves check for an admin), but the
# Menu rights table lists them so it matches the menu.
ADMIN_PAGES = {
    "admin": ("views/admin.py", "Admin", "🛡️"),
    "insights": ("views/insights.py", "Insights", "📈"),
    "menu_rights": ("views/menu_rights.py", "Menu rights", "🔐"),
}
VISITOR = "visitor"                                # someone who is not logged in
ROLES = [VISITOR, "renter", "owner"]               # the kinds of people an admin can configure
ROLE_NAMES = {VISITOR: "Visitor (not logged in)", "renter": "Renter", "owner": "Owner / landlord"}
# Pages a visitor does NOT get until the admin says so. They still show in the menu with a lock, and open a
# "Log in or sign up" prompt, so visitors can see what an account gives them.
VISITOR_OFF = {k for k in PAGES if k != "home"}   # a visitor sees Home only (Log in and Sign up are not in this list)
FILE_TO_KEY = {v[0]: k for k, v in PAGES.items()}


def _connect():
    con = db.connect()
    con.execute(DDL)
    return con


def is_locked(page_key):
    return PAGES[page_key][3]


def default_allowed(role, page_key):
    return not (role == VISITOR and page_key in VISITOR_OFF)


def is_fixed(role, page_key):
    """True when the admin cannot change this box: Home is always on, and visitors can never get any other page."""
    return role == VISITOR or is_locked(page_key)


def load_matrix():
    """{role: {page_key: bool}} for every configurable role and every page (defaults filled in)."""
    with _connect() as con:
        rows = con.execute("SELECT role, page_key, allowed FROM role_permissions").fetchall()
    saved = {(r, k): bool(a) for r, k, a in rows}
    return {role: {key: _value(role, key, saved) for key in PAGES} for role in ROLES}


def _value(role, key, saved):
    if role == VISITOR:                      # visitors: Home only, whatever an old saved row says
        return key == "home"
    return True if is_locked(key) else saved.get((role, key), default_allowed(role, key))


def save_matrix(matrix, admin_email=""):
    """matrix: {role: {page_key: bool}}. Unknown roles / pages are ignored; locked pages stay on."""
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    rows = [(role, key, int(_value(role, key, {(role, key): bool(matrix.get(role, {}).get(key, True))})), now, admin_email)
            for role in ROLES for key in PAGES]
    with _connect() as con:
        con.executemany("INSERT OR REPLACE INTO role_permissions(role, page_key, allowed, updated_at, updated_by) "
                        "VALUES (?,?,?,?,?)", rows)


def reset_defaults():
    with _connect() as con:
        con.execute("DELETE FROM role_permissions")


def allowed_pages(role):
    """Set of page keys this role may use. Admin: everything. Unknown role: only the locked pages."""
    role = role or VISITOR
    if role == "admin":
        return set(PAGES)
    if role not in ROLES:
        return {"home"}
    return {k for k, ok in load_matrix()[role].items() if ok}


def can_access(user, page_key):
    """user: the session user dict, or None for a visitor."""
    return page_key in allowed_pages(VISITOR if user is None else user.get("role"))


def role_from_db(user):
    """Current role straight from the database, so a role change works without logging in again."""
    with _connect() as con:
        row = con.execute("SELECT role FROM users WHERE user_id=?", (user["user_id"],)).fetchone()
    return row[0] if row else user.get("role")


def guard(page_key):
    """Call near the top of a page that can be switched off. Stops the page for a blocked role.
    A blocked visitor gets a log in / sign up prompt; a blocked account gets a plain message."""
    import streamlit as st
    import auth
    user = auth.current_user()
    role = VISITOR if user is None else role_from_db(user)
    if page_key in allowed_pages(role):
        return
    if user is None:
        st.info(f"Log in or create a free account to use {PAGES[page_key][1]}.")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.page_link("views/login.py", label="Log in", icon="🔑")
        with c2:
            st.page_link("views/signup.py", label="Sign up", icon="📝")
        st.stop()
    st.error("Your account type does not have access to this page. Ask the administrator if you need it.")
    st.stop()
