"""Dhaka House Rent Finder - website entry point (router).

Run:  python -m streamlit run app.py
First time only:  python train.py   then   python build_db.py
Pages live in views/. Backend: db.py, auth.py, maps.py, recommender.py, coverage.py, maintenance.py.
"""
import streamlit as st

import auth
import db
import ui

st.set_page_config(page_title="Dhaka House Rent Finder", page_icon="🏠", layout="wide")
ui.inject_css()

if not db.exists():
    st.error("The database is empty. In the terminal run `python train.py` and then `python build_db.py`, "
             "and reload this page.")
    st.stop()

user = auth.current_user()
pages = [
    st.Page("views/home.py", title="Home", icon="🏠", default=True),
    st.Page("views/find.py", title="Find a flat", icon="🔎"),
    st.Page("views/list_flat.py", title="List a flat", icon="➕"),
    st.Page("views/my_listing.py", title="Manage my listing", icon="✏️"),
    st.Page("views/dashboard.py", title="Dashboard", icon="📊"),
    st.Page("views/admin.py", title="Admin", icon="🛡️"),
    st.Page("views/about.py", title="About and privacy", icon="ℹ️"),
]
if user:
    pages.append(st.Page("views/account.py", title="My account", icon="👤"))
else:
    pages += [st.Page("views/login.py", title="Log in", icon="🔑"),
              st.Page("views/signup.py", title="Sign up", icon="📝")]

nav = st.navigation(pages)

ui.brand()
if user:
    st.sidebar.markdown(f'<div class="who"><b>{user["full_name"]}</b>{auth.ROLES.get(user["role"], "")}</div>',
                        unsafe_allow_html=True)
    if st.sidebar.button("Log out"):
        auth.logout()
        st.rerun()

nav.run()
