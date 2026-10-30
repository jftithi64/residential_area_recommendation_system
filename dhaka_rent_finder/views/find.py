"""Find a flat: needs -> ranked flats, map, compare, fair-rent calculator, survey."""
import json
import uuid

import numpy as np
import pandas as pd
import streamlit as st

import db
import recommender
import ui
from common import METRICS_PATH

KIND_LABELS = {"school": "School", "college": "College", "university": "University",
               "office": "Office", "area": "Any area / neighbourhood"}
NONE_LABEL = "I don't need distance (skip)"
PROVIDERS = ["OpenStreetMap (free)", "Google (needs your API key)"]

ui.inject_css()
ui.hero("Find a flat", "Tell us your budget and where you go every day. We rank real flats by total monthly cost, "
                       "price against similar flats, size and commute.")
st.session_state.setdefault("person_id", uuid.uuid4().hex[:10])


@st.cache_data(ttl=600)
def load_landmarks():
    return db.load_landmarks()


@st.cache_data(ttl=600)
def area_list():
    return recommender.places()


@st.cache_data(ttl=600)
def known_blocks():
    out = {}
    for place, sub in zip(*[db.load_listings()[c] for c in ("Place", "Sub")]):
        if isinstance(sub, str) and sub not in ("", "Unknown"):
            out.setdefault(place, set()).add(sub)
    return {k: sorted(v) for k, v in out.items()}


def model_error_pct():
    try:
        m = json.loads(METRICS_PATH.read_text())
        return float(m["block_holdout_metrics"][m["best"]]["MAPE_%"])
    except Exception:
        return 17.0


# ------------------------------------------------------------------ 1. needs
st.subheader("1. Your budget and flat")
c1, c2, c3, c4 = st.columns(4)
budget = c1.number_input("Highest rent you can pay (৳ / month)", min_value=1000, max_value=500000, value=25000, step=1000)
min_bed = c2.selectbox("Bedrooms: at least", [1, 2, 3, 4, 5], index=1)
max_bed = c3.selectbox("Bedrooms: at most", [1, 2, 3, 4, 5, 6], index=3)
min_bath = c4.selectbox("Bathrooms: at least", [1, 2, 3, 4], index=0)
if max_bed < min_bed:
    st.warning("'At most' is smaller than 'at least', so only flats with exactly the 'at least' number are shown.")
    max_bed = min_bed

# ------------------------------------------------------------------ 2. destination
st.subheader("2. Where do you go every day?")
lm = load_landmarks()
dest = None
present = [k for k in KIND_LABELS if not lm.empty and (lm.kind == k).any()]
if not present:
    st.info("No schools, colleges or offices are loaded yet, so distance is skipped. "
            "Run `python fetch_landmarks.py` and then `python build_db.py`.")
else:
    d1, d2 = st.columns([1, 2])
    kind_label = d1.selectbox("Type of place", [NONE_LABEL] + [KIND_LABELS[k] for k in present])
    if kind_label != NONE_LABEL:
        code = next(k for k, v in KIND_LABELS.items() if v == kind_label)
        opts = lm[lm.kind == code].dropna(subset=["lat", "lon"])
        label_of = {r.name: (r.name if code == "area" else f"{r.name} · {r.area}") for r in opts.itertuples()}
        pick = d2.selectbox(f"Search {kind_label.lower()}", opts.name.tolist(), index=None,
                            placeholder="Start typing a name...", format_func=lambda n: label_of.get(n, n))
        if pick:
            row = opts[opts.name == pick].iloc[0]
            dest = {"name": pick, "lat": float(row.lat), "lon": float(row.lon)}
        else:
            st.caption("Pick a place to measure distance, or choose 'skip' above.")

# ------------------------------------------------------------------ 3. preferences
st.subheader("3. Preferences")
p1, p2 = st.columns(2)
tenant_label = p1.selectbox("Who will live there?", recommender.TENANT_TYPES)
tenant = recommender.TENANT_CODES.get(tenant_label)
areas = p2.multiselect("Only these areas (leave empty for all areas)", area_list())

with st.expander("Advanced: distance limit, what matters most, cost assumptions"):
    a1, a2 = st.columns(2)
    max_km = a1.slider("Furthest distance (km, 0 = no limit)", 0, 40, 0)
    target_sqft = a1.number_input("Size you want (sqft, 0 = typical for this many bedrooms)", min_value=0,
                                  max_value=6000, value=0, step=50)
    strict = a2.checkbox("Hide flats whose tenant rule is unknown", value=False)
    owner_only = a2.checkbox("Only owner-listed flats (confirmed recently)", value=False)
    st.markdown("**What matters most** (0 = ignore, 10 = very important)")
    w = st.columns(4)
    w_value = w[0].slider("Good price for what it is", 0, 10, recommender.DEFAULT_WEIGHTS["w_value"])
    w_space = w[1].slider("Right size", 0, 10, recommender.DEFAULT_WEIGHTS["w_space"])
    w_commute = w[2].slider("Short commute", 0, 10, recommender.DEFAULT_WEIGHTS["w_commute"])
    w_savings = w[3].slider("Low rent", 0, 10, recommender.DEFAULT_WEIGHTS["w_savings"])
    st.markdown("**Cost assumptions** (guesses you can change)")
    k = st.columns(4)
    trips = k[0].number_input("Round trips per month", min_value=0, max_value=60,
                              value=recommender.TRIPS_PER_MONTH, step=1)
    fare = k[1].number_input("Fare per km (৳)", min_value=0.0, max_value=50.0,
                             value=float(recommender.FARE_PER_KM), step=0.5)
    walk = k[2].number_input("Walk if closer than (km)", min_value=0.0, max_value=5.0,
                             value=float(recommender.WALK_KM), step=0.5)
    adv_months = k[3].number_input("Advance deposit (months of rent)", min_value=0.0, max_value=12.0,
                                   value=float(recommender.ADVANCE_MONTHS), step=0.5)
    provider_label = st.radio("Distance source", PROVIDERS, horizontal=True)
    api_key = st.text_input("Google API key", type="password") if provider_label == PROVIDERS[1] else ""
    use_network = st.checkbox("Use the internet to measure road distance", value=True)
    top_n = st.slider("How many flats to show", 5, 30, 10)
    use_ranker = st.checkbox("Use the learned ranker if one has been trained", value=True)

go = st.button("Find flats", type="primary")
if go:
    with st.spinner("Measuring distances and scoring flats..."):
        pool = recommender.prepare(
            budget, min_bed=min_bed, max_bed=max_bed, min_bath=min_bath, target_sqft=target_sqft or None,
            preferred_places=areas or None, destination=dest, max_km=max_km or None, tenant=tenant,
            strict_tenant=strict, trips_per_month=trips, fare_per_km=fare, walk_km=walk,
            provider="google" if provider_label == PROVIDERS[1] else "osrm", api_key=api_key or None,
            use_network=use_network)
    if owner_only and not pool.empty:
        pool = pool[pool.is_extra.fillna(0) == 1]
    st.session_state["pool"] = pool
    st.session_state["search"] = {"budget": budget, "dest": dest, "max_km": max_km or None}
    st.session_state["pair"] = None
pool = st.session_state.get("pool")
search = st.session_state.get("search", {})

t_res, t_map, t_cmp, t_calc, t_survey = st.tabs(
    ["Results", "Map", "Compare", "Fair-rent calculator", "Help improve the ranking"])


def card(r, n, contacts):
    with st.container(border=True):
        left, mid, right = st.columns([3, 1.2, 1.4])
        left.markdown(f"**{n}. {r['Location']}**")
        tags = [("Owner-listed", "good")] if r.get("is_extra") == 1 else [("Market listing · availability not confirmed", "muted")]
        deal = r["deal_%"]
        if deal >= 35:
            tags.append(("Unusually cheap: verify before visiting", "warn"))
        elif deal >= 5:
            tags.append((f"{deal:.0f}% below typical rent", "good"))
        elif deal <= -5:
            tags.append((f"{abs(deal):.0f}% above typical rent", "warn"))
        else:
            tags.append(("Priced near typical rent", "info"))
        if pd.notna(r["km"]):
            tags.append((f"{r['km']:.1f} km" + (" (estimated)" if r["dist_source"] == "estimate" else " by road"), "info"))
        else:
            tags.append(("Distance unknown", "muted"))
        with left:
            ui.pills(tags)
        left.caption(f"{r['Sqft']:.0f} sqft · {int(r['Bed'])} bed · {int(r['Bath'])} bath · "
                     f"advance about {ui.money(r['advance'])}")
        if r.get("details"):
            left.caption(r["details"])
        if r.get("address_label"):
            left.caption(r["address_label"])
        mid.metric("Rent / month", ui.money(r["Price"]))
        right.metric("Rent + travel", ui.money(r["total_monthly"]),
                     help=f"Includes about {ui.money(r['travel_cost'])} a month for travel (an estimate from your "
                          "trips and fare assumptions).")
        contact = contacts.get(int(r["listing_id"]))
        if contact:
            right.caption(f"Contact: {contact}")
        url = r.get("source_url")
        if isinstance(url, str) and url.startswith("http"):
            right.markdown(f"[Original advert]({url})")


with t_res:
    if pool is None:
        st.info("Set your needs above and press **Find flats**.")
    elif pool.empty:
        st.warning("No flats match. Try a higher budget, fewer bedrooms, a longer distance limit, or all areas.")
    else:
        pool = pool.copy()
        pool["advance"] = pool.Price * adv_months
        ranked = recommender.rank(pool, max_km=search.get("max_km"), w_value=w_value, w_space=w_space,
                                  w_commute=w_commute, w_savings=w_savings, top_n=top_n, use_ranker=use_ranker)
        st.session_state["ranked"] = ranked
        st.caption(f"{len(pool)} flats match. Showing the best {len(ranked)}, at most 3 from the same block. "
                   "Change the sliders above to re-rank instantly.")
        contacts = db.public_contacts(ranked.listing_id.tolist())
        for n, (_, r) in enumerate(ranked.iterrows(), 1):
            card(r, n, contacts)

ranked = st.session_state.get("ranked")

with t_map:
    if ranked is None or ranked.empty:
        st.info("Search first to see the flats on a map.")
    else:
        pts = ranked.dropna(subset=["lat", "lon"])
        st.map(pts[["lat", "lon"]])
        st.caption("Dataset flats are placed at their block or area centre, so a few may overlap. "
                   + (f"Destination: {search['dest']['name']}." if search.get("dest") else ""))

with t_cmp:
    if ranked is None or ranked.empty:
        st.info("Search first, then pick flats here to compare side by side.")
    else:
        labels = {int(r.listing_id): f"{i}. {r.Location} ({ui.money(r.Price)})"
                  for i, r in enumerate(ranked.itertuples(), 1)}
        chosen = st.multiselect("Pick up to 4 flats", list(labels), default=list(labels)[:2],
                                format_func=lambda i: labels[i], max_selections=4)
        if chosen:
            sub = ranked[ranked.listing_id.isin(chosen)]
            table = pd.DataFrame({
                f"#{i + 1}": {
                    "Where": r["Location"], "Rent": ui.money(r["Price"]), "Rent + travel": ui.money(r["total_monthly"]),
                    "Size (sqft)": f"{r['Sqft']:.0f}", "Bedrooms": int(r["Bed"]), "Bathrooms": int(r["Bath"]),
                    "Distance": "unknown" if pd.isna(r["km"]) else f"{r['km']:.1f} km",
                    "Vs typical rent": f"{r['deal_%']:+.0f}%", "Score": r["score"],
                    "Details": r.get("details") or "-"}
                for i, (_, r) in enumerate(sub.iterrows())})
            ui.show_df(table)

with t_calc:
    st.markdown("Estimate a typical asking rent for any flat, for example to check an advert.")
    blocks = known_blocks()
    q1, q2 = st.columns(2)
    calc_area = q1.selectbox("Area", area_list(), key="calc_area")
    calc_sub = q2.selectbox("Block / sub-area", ["Unknown"] + blocks.get(calc_area, []), key="calc_sub")
    q3, q4, q5 = st.columns(3)
    calc_sqft = q3.number_input("Size (sqft)", min_value=250, max_value=6000, value=900, step=50, key="calc_sqft")
    calc_bed = q4.number_input("Bedrooms", min_value=1, max_value=10, value=2, key="calc_bed")
    calc_bath = q5.number_input("Bathrooms", min_value=1, max_value=10, value=2, key="calc_bath")
    if st.button("Estimate rent", key="calc_go"):
        fair = recommender.predict_fair_rent(calc_area, calc_sub, float(calc_sqft), int(calc_bed), int(calc_bath))
        err = model_error_pct() / 100
        st.metric("Typical asking rent", ui.money(round(fair, -2)))
        st.caption(f"The model is usually within about {err * 100:.0f}% on new blocks, so a rent between "
                   f"{ui.money(fair * (1 - err))} and {ui.money(fair * (1 + err))} is normal for this kind of flat.")


def record(choice_a):
    """Save one A/B answer, with the features the learned ranker will train on."""
    p = st.session_state.get("pool")
    pair = st.session_state.get("pair")
    if p is None or pair is None:
        return
    idx = p.set_index("listing_id", drop=False)
    a, b = idx.loc[pair[0]], idx.loc[pair[1]]
    s = st.session_state.get("search", {})
    db.add_pair(st.session_state["person_id"], (s.get("dest") or {}).get("name", ""), pair[0], pair[1], choice_a,
                recommender.feature_dict(a), recommender.feature_dict(b),
                {"budget_max": s.get("budget"), "max_km": s.get("max_km") or 10.0, "use_commute": bool(s.get("dest"))})
    st.session_state["pair"] = None
    st.session_state["answered"] = st.session_state.get("answered", 0) + 1


def skip_pair():
    st.session_state["pair"] = None


with t_survey:
    st.markdown("Which of two flats would you pick? Your answers are saved anonymously and teach the ranking what "
                "people like you prefer. 15 to 20 answers help a lot.")
    if pool is None or pool.empty or len(pool) < 2:
        st.info("Search first; this tab uses flats that match your needs.")
    else:
        pair = st.session_state.get("pair")
        ids = set(pool.listing_id.astype(int))
        if pair is None or pair[0] not in ids or pair[1] not in ids:
            a_id, b_id = np.random.choice(pool.listing_id.to_numpy(), 2, replace=False)
            pair = (int(a_id), int(b_id))
            st.session_state["pair"] = pair
        idx = pool.set_index("listing_id", drop=False)
        cols = st.columns(2)
        for col, name, lid in zip(cols, ["A", "B"], pair):
            r = idx.loc[lid]
            with col.container(border=True):
                st.markdown(f"**Flat {name}**")
                st.markdown(f"{ui.money(r['Price'])} per month")
                st.caption(f"{r['Sqft']:.0f} sqft · {int(r['Bed'])} bed · {int(r['Bath'])} bath")
                st.caption("distance unknown" if pd.isna(r["km"]) else f"{r['km']:.1f} km away")
                st.caption(f"{r['deal_%']:+.0f}% vs typical rent · travel about {ui.money(r['travel_cost'])} / month")
        b1, b2, b3 = st.columns(3)
        b1.button("I prefer A", on_click=record, args=(1,), key="pref_a")
        b2.button("I prefer B", on_click=record, args=(0,), key="pref_b")
        b3.button("Can't decide / skip", on_click=skip_pair, key="pref_skip")
        st.caption(f"Answers from you so far: {st.session_state.get('answered', 0)}")
