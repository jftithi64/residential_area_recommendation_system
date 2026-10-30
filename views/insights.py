"""Insights (admin): sign-ups, listed flats, the review queue and what people are interested in."""
import streamlit as st

import auth
import insights
import ui

ui.inject_css()
ui.hero("Insights", "How many people sign up, how many flats are listed, how the review is going, and what people want.")

auth.require_admin()

days = st.selectbox("Period for the daily charts", [7, 30, 90], index=1, format_func=lambda d: f"Last {d} days")
su, ls, rv = insights.signup_summary(), insights.listing_summary(), insights.review_stats()

c = st.columns(5)
c[0].metric("People signed up", su["total"], f"+{su['last7']} this week")
c[1].metric("Renters", su["renters"])
c[2].metric("Owners", su["owners"])
c[3].metric("Flats listed by people", ls["total"], f"+{ls['last7']} this week")
c[4].metric("Waiting for review", rv["waiting"])

t_sign, t_list, t_rev, t_int = st.tabs(["Sign-ups", "Listed flats", "Review", "Interests"])

with t_sign:
    users = insights.users_df()
    st.markdown("**New sign-ups per day**")
    st.bar_chart(insights.daily_counts(users.created_at, days))
    st.markdown("**Total people over time**")
    per_day = insights.daily_counts(users.created_at, days)["count"]
    before = int((users.created_at < per_day.index[0]).sum()) if len(users) else 0
    st.line_chart((per_day.cumsum() + before).rename("people").to_frame())
    a, b = st.columns(2)
    with a:
        st.markdown("**Renters and owners**")
        st.bar_chart(users.role.value_counts().rename("people").to_frame())
    with b:
        st.markdown("**Account health**")
        st.write(f"Email verified: **{su['verified']}** of {su['total']}")
        st.write(f"Logged in during the last 7 days: **{su['active7']}**")
        st.write(f"New in the last 30 days: **{su['last30']}**")

with t_list:
    flats = insights.owner_listings()
    st.markdown("**Flats added per day**")
    st.bar_chart(insights.daily_counts(flats.listed_at, days))
    a, b = st.columns(2)
    with a:
        st.markdown("**Flats by status**")
        st.bar_chart(insights.status_counts())
    with b:
        st.markdown("**Live owner flats by area (top 15)**")
        by_area = insights.listings_by_area()
        if by_area.empty:
            st.caption("No live owner flats yet.")
        else:
            st.bar_chart(by_area)
    st.caption("Counts every flat added through the site or imported by the admin. Flats are not tied to an account, "
               "so the number of different owners who listed cannot be shown.")

with t_rev:
    r = st.columns(4)
    r[0].metric("Waiting now", rv["waiting"])
    r[1].metric("Oldest waiting (days)", "-" if rv["oldest_days"] is None else rv["oldest_days"])
    r[2].metric("Reviewed", rv["reviewed"])
    r[3].metric("Turned down", "-" if rv["rejected_pct"] is None else f"{rv['rejected_pct']}%")
    st.bar_chart(insights.status_counts())
    st.caption("Open the Admin page, Review queue tab, to approve or reject waiting entries.")

with t_int:
    it = insights.interest_summary()
    if it["people"] == 0:
        st.caption("Nobody has filled in interests yet. They are asked at sign-up and can be edited on My account.")
    else:
        st.write(f"**{it['people']}** people told us what they want.")
        a, b = st.columns(2)
        with a:
            st.markdown("**What brings them here**")
            st.bar_chart(it["purposes"])
            st.markdown("**Bedrooms wanted**")
            st.bar_chart(it["bedrooms"])
        with b:
            st.markdown("**Highest rent they can pay**")
            st.bar_chart(it["budget"])
            st.markdown("**Most wanted areas**")
            st.bar_chart(it["areas"])
        st.markdown("**Areas people want, and how many live owner flats they have**")
        st.caption("Areas with many interested people and few flats are where to look for new listings first.")
        ui.show_df(insights.demand_vs_supply().reset_index(names="Area"), hide_index=True)
