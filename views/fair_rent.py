"""Is my rent fair? A free check that needs no account and no listings."""
import json

import pandas as pd
import streamlit as st

import db
import recommender
import permissions
import ui
from common import AREA_COORDS, METRICS_PATH
from flatcard_logic import fair_verdict

ui.inject_css()
permissions.guard("fair_rent")
ui.hero("Is my rent fair?", "Enter the flat and the rent. We compare it with what similar flats in the same area ask.")


def model_error_pct():
    """Typical error of the rent model on blocks it has never seen (from models/metrics.json)."""
    try:
        m = json.loads(METRICS_PATH.read_text())
        return float(m["block_holdout_metrics"][m["best"]]["MAPE_%"])
    except Exception:
        return 17.0


@st.cache_data(ttl=600)
def listings():
    df = db.load_listings()
    live = df.status.fillna("approved").eq("approved") & df.entry_kind.fillna("available").eq("available")
    return df[live]


df = listings()
areas = sorted(set(df.Place.unique()) | set(AREA_COORDS))   # areas with listings, plus the extra Dhaka areas
err = model_error_pct()

form_col, out_col = st.columns([1, 1.3], gap="large")
with form_col:
    with st.form("fair_form"):
        place = st.selectbox("Area", areas, index=areas.index("Mirpur") if "Mirpur" in areas else 0)
        blocks = sorted(b for b in df[df.Place == place].Sub.dropna().unique() if b not in ("Unknown", ""))
        sub = st.selectbox("Block or road (optional)", ["Not sure"] + blocks)
        c1, c2, c3 = st.columns(3)
        sqft = c1.number_input("Size (sqft)", 250, 6000, 1000, step=50)
        bed = c2.number_input("Bedrooms", 1, 10, 2)
        bath = c3.number_input("Bathrooms", 1, 10, 2)
        rent = st.number_input("Rent per month (৳)", 0, 500000, 0, step=500,
                               help="Leave at 0 to see only the typical rent.")
        go = st.form_submit_button("Check rent", type="primary")

with out_col:
    if not go:
        st.info("Fill in the flat on the left and press Check rent.")
    else:
        fair = recommender.predict_fair_rent(place, "" if sub == "Not sure" else sub, float(sqft), int(bed), int(bath))
        proxies = recommender.proxy_areas(place)
        shown_err = max(err, 25.0) if proxies else err   # an area without data is a rougher guess
        low, high = fair * (1 - shown_err / 100), fair * (1 + shown_err / 100)
        if proxies:
            st.warning(f"We have no rent data for {place} yet, so this is borrowed from nearby areas: "
                       + ", ".join(f"{a} ({d:.1f} km)" for a, d in proxies) + ". Treat it as a rough guide.")
        st.markdown(f'<div class="verdict"><div>Typical asking rent for this flat</div>'
                    f'<div class="big">{ui.money(round(fair, -2))}</div>'
                    f'<div>Likely range {ui.money(round(low, -2))} to {ui.money(round(high, -2))} a month</div></div>',
                    unsafe_allow_html=True)
        if rent > 0:
            gap, text, kind = fair_verdict(float(rent), fair, err)
            st.write("")
            word = "above" if gap > 0 else "below"
            ui.pills([(f"{abs(gap):.0f}% {word} typical", kind)])
            st.write(text)
        similar = df[(df.Place == place) & (df.Bed == bed) & df.Sqft.between(sqft * 0.75, sqft * 1.25)]
        if len(similar) >= 5:
            st.write(f"{len(similar)} similar flats in {place} ask a middle rent of {ui.money(similar.Price.median())}, "
                     f"mostly between {ui.money(similar.Price.quantile(.25))} and {ui.money(similar.Price.quantile(.75))}.")
        st.caption(f"This is an estimate from asking rents, not a price list. On blocks the model has never seen, "
                   f"it is off by about {shown_err:.0f}% on average. Floor, lift, gas and the owner's rules also change the rent.")
