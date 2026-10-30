"""Home page.

Visitors (not logged in) see a clean landing page: one clear message (log in, or sign up), the site's numbers,
how the ranking works and the reviews. They cannot search from here.
Logged-in people get the quick search box.
"""
import streamlit as st

import auth
import cards
import coverage
import db
import ui

ui.inject_css()
user = auth.current_user()
_new = st.session_state.pop("account_created", None)
if _new and user:
    st.success(f"Account created successfully. Welcome, {_new}! You are now logged in.")

s = coverage.summary(db.load_listings())
n_users = db.count_users()


def numbers(cols):
    with cols[0]:
        ui.tile(f"{n_users:,}", "people with an account")
    with cols[1]:
        ui.tile(f"{s['live_total']:,}", "flats in the search")
    with cols[2]:
        ui.tile(s["areas"], "areas of Dhaka")
    with cols[3]:
        ui.tile(f"{s['user_live']:,}", "confirmed by their owners")


def reviews_section():
    """Reviews as cards in a scrolling box (so many reviews never make the page long) beside a write-a-review box."""
    st.subheader("What people say")
    write, read = st.columns([2, 3], gap="large")
    with write:
        with st.container(border=True):
            st.markdown("**Write a review**")
            if user is None:
                st.caption("Log in to share what you think of the site.")
            else:
                ui.review_form(user, "home_review_form")
    # read after the form above, so a review saved just now already shows in the list
        rs = db.review_stats()
    reviews = db.latest_reviews(100)
    with read:
        if rs["average"] is not None:
            st.markdown(f'{ui.stars(rs["average"])} <b>{rs["average"]} / 5</b> from {rs["count"]} review(s)',
                        unsafe_allow_html=True)
        if not reviews:
            st.caption("No reviews yet. Be the first to write one.")
            return
        box = st.container(height=420) if len(reviews) > 3 else st.container()
        with box:
            for r in reviews:
                st.markdown(ui.review_card(r), unsafe_allow_html=True)


def how_it_works():
    st.subheader("How we rank flats")
    h1, h2, h3 = st.columns(3, gap="large")
    with h1:
        ui.feature("feat_fair_rent.svg", "**Fair rent.** A model trained on thousands of Dhaka asking rents estimates what a flat "
                   "like this usually costs, and flags rents far above or below it.")
    with h2:
        ui.feature("feat_distance.svg", "**Real distance.** We measure road distance to your destination and add an estimate of "
                   "what the daily trip costs, so a cheap flat far away does not look cheaper than it is.")
    with h3:
        ui.feature("feat_priorities.svg", "**Your priorities.** Rent, space and distance are combined into one score, and the "
                   "order improves as more renters tell us which flat they prefer.")


# =================================================================== visitor
if not user:
    ui.hero("Find a flat in Dhaka at a fair rent",
            "See what a flat should cost, how far it is from your school or office, and who is renting it out.")

    with st.container(border=True):
        st.subheader("Log in to search flats")
        st.write("Searching flats, checking your rent and listing a flat are for members. It is free.")
        ui.link("views/login.py", "Log in", "🔑")
        st.markdown('<div class="sign-line">Don\'t have an account?</div>', unsafe_allow_html=True)
        ui.link("views/signup.py", "Sign up", "📝")
    st.write("")

    numbers(st.columns(4))
    st.write("")
    how_it_works()
    st.write("")
    reviews_section()
    st.stop()

# =================================================================== logged in
ui.hero("Find a flat you can afford, close to where you go every day",
        "Tell us your rent budget and your school or office. We rank flats by rent plus travel cost, "
        "and tell you when a rent looks too high.")

lm = cards.landmark_table()
labels = ["No destination"] + lm["label"].tolist()
with st.form("quick_search"):
    c1, c2, c3, c4 = st.columns([1.1, 0.9, 2.2, 1])
    budget = c1.number_input("Highest rent a month (৳)", 3000, 500000, 20000, step=1000)
    bed = c2.selectbox("Bedrooms", [1, 2, 3, 4, 5], index=1)
    dest = c3.selectbox("School, college, university, office or area", labels)
    c4.write("")
    go = c4.form_submit_button("Show flats", type="primary")
if go:
    st.session_state["prefs"] = {"budget": budget, "bed": bed, "dest": dest}
    st.session_state.pop("browse_df", None)
    ui.goto("views/browse.py")

numbers(st.columns(4))
st.write("")
if s["user_live"] < 50:
    st.info("Most flats here come from a public dataset of asking rents, so they are marked as not confirmed. "
            "Flats added by owners show a green Confirmed tag, a contact button and photos.")

a, b = st.columns(2, gap="large")
with a:
    with st.container(border=True):
        st.markdown(f'<div class="feat"><img src="{ui.asset_uri("illus_renter.svg")}" alt=""></div>', unsafe_allow_html=True)
        st.subheader("Is my rent fair?")
        st.write("Paying for a flat already? Enter the area, size and rent to see how it compares.")
        ui.link("views/fair_rent.py", "Check my rent", "⚖️")
with b:
    with st.container(border=True):
        st.markdown(f'<div class="feat"><img src="{ui.asset_uri("illus_owner.svg")}" alt=""></div>', unsafe_allow_html=True)
        st.subheader("Own a flat to rent?")
        st.write("List it for free, add photos, and reach renters who already know their budget.")
        ui.link("views/list_flat.py", "List a flat", "➕")

st.write("")
how_it_works()
st.write("")
reviews_section()
