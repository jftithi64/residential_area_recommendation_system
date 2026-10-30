"""About: how it works, accuracy, limits and privacy."""
import json

import streamlit as st

import maps
import ui
from common import METRICS_PATH

ui.inject_css()
ui.hero("About and privacy", "What the numbers mean, how accurate they are, and what we store.")

st.subheader("How the pieces work")
st.markdown(
    "- **Typical asking rent** comes from a machine-learning model trained on past advertised rents using area, "
    "block, size, bedrooms and bathrooms. It is a reference, not a valuation. It cannot see floor, lift, view or the "
    "condition of the flat.\n"
    "- **Distance** is by road from the flat's block (or exact address, if the owner gave one) to your destination. "
    "Free OpenStreetMap times ignore traffic.\n"
    "- **Total monthly cost** = rent + an estimated travel cost (round trips x the fare for each flat's distance). "
    "You pick a vehicle (bus, metro, rickshaw, CNG, ride-share, your own motorbike, walking or your own rate) and the "
    "fare is worked out from the distance with that vehicle's rate per km (fare = starting fare + km x rate, never below "
    "the minimum fare). The rates are typical estimates, not official tariffs, and you can edit them. Walking distance "
    "costs nothing.\n"
    "- **Ranking** is a weighted score you control with sliders. If enough survey answers have been collected, a "
    "learned ranker is blended in.")

st.subheader("How accurate is the rent model?")
try:
    m = json.loads(METRICS_PATH.read_text())
    best = m["best"]
    rnd, blk = m["test_metrics"][best], m["block_holdout_metrics"][best]
    c = st.columns(3)
    c[0].metric("Model", best)
    c[1].metric("Average error, known blocks", f"{rnd['MAPE_%']}%")
    c[2].metric("Average error, new blocks", f"{blk['MAPE_%']}%")
    st.caption(f"Tested on listings the model had not seen. About {blk['within_20%']}% of new-block predictions are "
               "within 20% of the advertised rent.")
except Exception:
    st.caption("Train the model (`python train.py`) to see accuracy figures here.")

st.subheader("Limits you should know")
st.markdown(
    "- Rents are **asking prices**, not what people finally pay.\n"
    "- Many flats come from an older collection and may already be rented. Flats marked *Owner-listed* are confirmed "
    "within the last 45 days; older ones are hidden automatically.\n"
    "- The original data has no street address, floor, lift or gas information.\n"
    "- Dataset flats are located at block or area level, so distances are approximate for them.\n"
    "- Entries with a rent far from the typical level are held for an admin to check before they appear.")

st.subheader("Privacy")
st.markdown(
    "- Contact details are optional. They are shown only if the owner ticks the box to show them, and only while the "
    "flat is live.\n"
    "- The edit code is stored only as a salted hash. Nobody, including the admin, can read it back, so keep it safe.\n"
    "- Survey answers are stored with a random anonymous id, never your name or phone number.\n"
    "- This is a student project: do not send money to anyone you have not met.")

st.caption(maps.CREDIT)
