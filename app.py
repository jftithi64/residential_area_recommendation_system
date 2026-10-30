"""Dhaka House Rent Finder - website entry point (router).

Run:  python -m streamlit run app.py
First time only:  python train.py   then   python build_db.py
Pages live in views/. Backend: db.py, auth.py, maps.py, recommender.py, coverage.py, maintenance.py.
"""
from pathlib import Path

import streamlit as st

import auth
import db
import permissions
import ui

st.set_page_config(page_title="Dhaka House Rent Finder", layout="wide",
                   page_icon=str(Path(__file__).parent / "assets" / "favicon.png"))
ui.inject_css()

if not db.exists():
    st.error("The database is empty. In the terminal run `python train.py` and then `python build_db.py`, "
             "and reload this page.")
    st.stop()

auth.ensure_admin_account()   # admin login comes from ADMIN_EMAIL / ADMIN_PASSWORD in .env
user = auth.current_user()
role = permissions.role_from_db(user) if user else permissions.VISITOR
allowed = permissions.allowed_pages(role)
PAGES = permissions.PAGES
pages = []
if not user:
    # A visitor sees ONLY Home, Log in and Sign up. Searching flats, listing a flat, the dashboard and every
    # other page need an account (permissions.py enforces the same rule on each page).
    pages = [st.Page(PAGES["home"][0], title="Home", icon="🏠", default=True),
             st.Page("views/login.py", title="Log in", icon="🔑"),
             st.Page("views/signup.py", title="Sign up", icon="📝")]
else:
    for key, (file, title, icon, _locked) in PAGES.items():
        if key in ("about", "account"):
            continue
        if key in allowed:
            pages.append(st.Page(file, title=title, icon=icon, default=(key == "home")))
    if auth.is_admin(user):
        pages += [st.Page(f, title=t, icon=i) for f, t, i in permissions.ADMIN_PAGES.values()]
    pages.append(st.Page(PAGES["about"][0], title=PAGES["about"][1], icon=PAGES["about"][2]))
    pages.append(st.Page("views/account.py", title="My account", icon="👤"))

nav = st.navigation(pages)
if st.session_state.pop("goto_home_once", False) and user:   # just created an account: show the Home page
    st.switch_page("views/start.py")
_after = st.session_state.pop("after_login", None)   # set by the Log in page; the menu now matches the person
if _after and user:
    if _after == "admin" and auth.is_admin(user):
        st.switch_page("views/admin.py")
    elif "browse" in allowed:
        st.switch_page("views/browse.py")
    else:
        st.switch_page("views/start.py")

ui.brand()
if user:
    st.sidebar.markdown(f'<div class="who"><b>{user["full_name"]}</b>{auth.ROLE_LABELS.get(user["role"], "")}</div>',
                        unsafe_allow_html=True)
    if st.sidebar.button("Log out"):
        auth.logout()
        st.rerun()

nav.run()
