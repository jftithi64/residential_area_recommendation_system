"""My account: profile summary and log-out."""
import streamlit as st

import auth
import db
import listing_logic
import ui

ui.inject_css()
user = auth.require_login()
ui.hero("My account", "Your details.")

c1, c2, c3 = st.columns(3)
with c1:
    ui.tile(auth.ROLE_LABELS.get(user["role"], user["role"]), "Account type")
with c2:
    ui.tile((user.get("created_at") or "today")[:10], "Member since")
with c3:
    ui.tile(user["phone"], "Mobile number")

st.write("")
st.markdown(f"**Name:** {user['full_name']}  \n**Email:** {user['email']}")
st.write("")
st.subheader("My review")
st.caption("Tell other people what you think of the site. It is shown on the home page with your name.")
ui.review_form(user)
st.write("")
if not auth.is_admin(user):
    st.write("")
    st.subheader("My interests")
    cur = auth.get_interests(user["user_id"])
    with st.form("interests_form"):
        purposes = st.multiselect("What brings you here?", auth.PURPOSES,
                                  default=[p for p in cur["purposes"] if p in auth.PURPOSES])
        areas_i = st.multiselect("Areas you are interested in", listing_logic.area_names(),
                                 default=[a for a in cur["areas"] if a in listing_logic.area_names()])
        i1, i2 = st.columns(2)
        beds = ["Any", 1, 2, 3, 4, 5]
        bed_i = i1.selectbox("Bedrooms you need", beds, index=beds.index(cur["bedrooms"]) if cur["bedrooms"] in beds else 0)
        budget_i = i2.number_input("Highest rent a month (৳)", 0, 500000, int(cur["budget_max"] or 0), step=1000,
                                   help="Leave at 0 to skip.")
        if st.form_submit_button("Save interests"):
            auth.save_interests(user["user_id"], purposes, areas_i, None if bed_i == "Any" else bed_i, budget_i or None)
            st.success("Saved.")
st.write("")
st.write("")
if st.button("Log out"):
    auth.logout()
    st.switch_page("views/start.py")
