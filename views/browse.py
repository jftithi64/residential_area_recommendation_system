"""Browse flats: filters on the left, ranked flat cards (or a map) on the right."""
import numpy as np
import pandas as pd
import streamlit as st

import auth
import cards
import db
import photos
import recommender
import permissions
import ui

ui.inject_css()
permissions.guard("browse")
ui.hero("Browse flats", "Ranked by fair rent, space and how far the flat is from where you go every day.")

state = st.session_state
prefs = state.get("prefs", {})
lm = cards.landmark_table()
labels = ["No destination"] + lm["label"].tolist()
default_dest = labels.index(prefs["dest"]) if prefs.get("dest") in labels else 0
sort_options = ["Best match", "Lowest rent", "Closest first"]

filters, results = st.columns([1, 2.4], gap="large")

with filters:
    with st.form("browse_form"):
        st.subheader("Your search")
        budget = st.number_input("Highest rent a month (৳)", 3000, 500000, int(prefs.get("budget", 20000)), step=1000)
        beds = st.selectbox("Bedrooms (at least)", [1, 2, 3, 4, 5], index=int(prefs.get("bed", 2)) - 1)
        dest_label = st.selectbox("Where do you go every day?", labels, index=default_dest,
                                  help="A school, college, university, office or area. Type to search.")
        max_km = st.slider("Farthest distance (km)", 1, 30, 10)
        tenant = st.selectbox("Who will live there?", recommender.TENANT_TYPES)
        areas = st.multiselect("Only these areas (optional)", recommender.places())
        sort_by = st.radio("Sort by", sort_options)
        online = st.checkbox("Measure real road distance (needs internet)", value=True)
        go = st.form_submit_button("Show flats", type="primary")

if go or "browse_df" not in state:
    dest = None
    if dest_label != "No destination":
        row = lm[lm.label == dest_label].iloc[0]
        dest = {"name": row["name"], "lat": float(row["lat"]), "lon": float(row["lon"])}
    try:
        with st.spinner("Finding flats..."):
            pool = recommender.prepare(
                budget, max_km=max_km if dest else None, min_bed=int(beds), preferred_places=areas or None,
                destination=dest, use_network=online, tenant=recommender.TENANT_CODES.get(tenant))
            ranked = recommender.rank(pool, max_km=max_km if dest else None, top_n=500, max_per_block=3)
            # Flats added by owners are confirmed and few, so they are always shown first. Without this a flat
            # at the top of the budget can rank below the best 24 of thousands of dataset flats and never appear.
            if ranked.empty:
                df = ranked
            else:
                mine = ranked[ranked.is_extra.fillna(0) == 1].head(12)
                rest = ranked[~ranked.listing_id.isin(mine.listing_id)].head(max(24 - len(mine), 12))
                df = pd.concat([mine, rest])
        if sort_by == "Lowest rent" and not df.empty:
            df = df.sort_values("Price")
        elif sort_by == "Closest first" and dest and not df.empty:
            df = df.sort_values("km")
        state["browse_df"], state["browse_dest"], state["browse_dest_xy"] = df, (dest or {}).get("name"), dest
        state["browse_total"] = int(len(pool))
    except Exception as e:
        st.error(f"Could not search. Run train.py and build_db.py first. ({e.__class__.__name__}: {e})")
        st.stop()

df, dest_name = state["browse_df"], state.get("browse_dest")

with results:
    if df.empty:
        st.subheader("No flats match yet")
        st.write("Try a higher rent, fewer bedrooms, a longer distance, or remove the area filter.")
        st.stop()
    live = auth.current_user() is not None
    confirmed = int((df.is_extra.fillna(0) == 1).sum())
    total = state.get("browse_total", len(df))
    shown = f"Showing the best **{len(df)}** of **{total:,}** flats that match." if total > len(df) else f"**{len(df)} flats** match."
    st.write(f"{shown} {confirmed} confirmed by owners.")
    list_tab, map_tab = st.tabs(["List", "Map"])
    with list_tab:
        ids = df.listing_id.astype(int).tolist()
        contacts, pics = db.public_contacts(ids), photos.first_photos(ids)
        for _, r in df.iterrows():
            lid = int(r.listing_id)
            cards.flat_card(r, dest_name=dest_name, contact=contacts.get(lid), photo=pics.get(lid), logged_in=live)
    with map_tab:
        pts = df.dropna(subset=["lat", "lon"])[["lat", "lon"]].copy()
        # Flats of one block share one coordinate, so their pins would sit on top of each other (one dot).
        # Spread them on a small circle (about 150 m) around the block so every flat is visible.
        pts["_k"] = pts.lat.round(5).astype(str) + "," + pts.lon.round(5).astype(str)
        for _, grp in pts.groupby("_k"):
            n = len(grp)
            if n > 1:
                ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
                pts.loc[grp.index, "lat"] = grp.lat.values + 0.0013 * np.sin(ang)
                pts.loc[grp.index, "lon"] = grp.lon.values + 0.0013 * np.cos(ang)
        pts = pts[["lat", "lon"]]
        pts["color"], pts["size"] = "#0b6b5c", 60
        dxy = state.get("browse_dest_xy")
        if dxy:   # the place the person goes every day, as one big blue pin
            pts.loc[len(pts)] = [dxy["lat"], dxy["lon"], "#1f5fbf", 160]
        st.map(pts, latitude="lat", longitude="lon", color="color", size="size")
        st.caption("Green pins are flats" + (", the big blue pin is " + str(dest_name) if dxy else "") +
                   ". Pins sit at the block or area, not at the exact building (flats in one block are spread "
                   "slightly so you can see each one), except for flats whose owner gave a map position.")
