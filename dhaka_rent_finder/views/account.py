"""My account: profile summary and log-out."""
import streamlit as st

import auth
import ui

ui.inject_css()
user = auth.require_login()
ui.hero("My account", "Your details and shortcuts.")

c1, c2, c3 = st.columns(3)
with c1:
    ui.tile(auth.ROLES.get(user["role"], user["role"]), "Account type")
with c2:
    ui.tile((user.get("created_at") or "today")[:10], "Member since")
with c3:
    ui.tile(user["phone"], "Mobile number")

st.write("")
st.markdown(f"**Name:** {user['full_name']}  \n**Email:** {user['email']}")
st.write("")
ui.link("views/list_flat.py", "List a flat", "➕")
ui.link("views/my_listing.py", "Manage my listing", "✏️")
st.write("")
if st.button("Log out"):
    auth.logout()
    st.switch_page("views/home.py")
