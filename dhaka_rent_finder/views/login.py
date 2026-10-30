"""Log-in page: email or mobile number plus password."""
import streamlit as st

import auth
import ui

ui.inject_css()
ui.hero("Welcome back", "Log in to manage your listings and saved searches.")

user = auth.current_user()
if user:
    st.success(f"You are signed in as {user['full_name']}.")
    ui.link("views/find.py", "Find a flat", "🔎")
    st.stop()

_, mid, _ = st.columns([1, 2, 1])
with mid:
    with st.form("login_form"):
        who = st.text_input("Email or mobile number")
        password = st.text_input("Password", type="password")
        go = st.form_submit_button("Log in", type="primary")
    if go:
        found, msg = auth.authenticate(who, password)
        if found is None:
            st.error(msg)
        else:
            auth.login(found)
            st.switch_page("views/find.py")
    st.write("New here?")
    ui.link("views/signup.py", "Create an account", "➕")
