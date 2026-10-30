"""Home: what the site does, live numbers, where to go next."""
import streamlit as st

import coverage
import db
import ui

ui.inject_css()
ui.hero("Find a Dhaka flat that fits your budget and your daily trip",
        "We measure the road distance to your school, college or office, estimate a fair rent with machine "
        "learning, add up the real monthly cost, and rank specific flats for you.")

s = coverage.summary(db.load_listings())
c = st.columns(4)
c[0].metric("Flats in the database", f"{s['live_total']:,}")
c[1].metric("Owner-listed (confirmed)", f"{s['user_live']:,}")
c[2].metric("Areas covered", f"{s['areas']:,}")
c[3].metric("Added in the last 30 days", f"{s['added_30d']:,}")

st.write("")
a, b, d = st.columns(3)
with a.container(border=True):
    st.markdown("#### 🔎 I am looking for a flat")
    st.caption("Set a budget, pick where you go every day, and get a ranked list with the total monthly cost.")
    ui.link("views/find.py", "Find a flat", "🔎")
with b.container(border=True):
    st.markdown("#### ➕ I have a flat to rent")
    st.caption("Add it in two minutes. You get a private code to change the rent or mark it rented.")
    ui.link("views/list_flat.py", "List a flat", "➕")
with d.container(border=True):
    st.markdown("#### 📊 Where is data missing?")
    st.caption("See how many flats each area has and which areas need fresher listings.")
    ui.link("views/dashboard.py", "Open the dashboard", "📊")

st.subheader("How it works")
st.markdown(
    "1. **You tell us** your highest rent, how many bedrooms you need and where you go every day.\n"
    "2. **We measure** the road distance from each flat's block to that place (OpenStreetMap).\n"
    "3. **We estimate** a typical asking rent for a similar flat, so you can see which flats are priced well.\n"
    "4. **We rank** flats by price, fit, size and commute, and show the real monthly cost including travel.")

st.info("**Please read:** most flats here come from a past collection of asking prices and their availability is "
        "**not confirmed**. Flats marked *Owner-listed* were added by their owner and confirmed recently. "
        "Always call and visit before paying anything.")
