"""List a flat (or share the rent you pay). Nearby areas are suggested live so distances can be checked."""
from datetime import date

import pandas as pd
import streamlit as st

import db
import listing_logic
import nearby
import recommender
import ui

OTHER, UNSURE = "Other (type it below)", "Not sure / not listed"
YN = ["Not sure", "Yes", "No"]
RULES = ["Not sure"] + list(listing_logic.TENANT_RULES)

ui.inject_css()
ui.hero("List a flat", "Add a flat that is for rent, or share the rent you pay now. An admin checks every entry "
                       "before it appears. You get a private code to change or remove it later.")


def yn(v):
    return {"Yes": 1, "No": 0}.get(v)


kind = st.radio("What are you adding?", ["A flat that is available for rent", "The rent I pay now (not advertised)"],
                horizontal=True)
paid = kind.startswith("The rent")
if paid:
    st.caption("Rents people really pay help us test the price model. They are never shown to renters as available flats.")

# ---- step 1 is outside the form so the nearby list updates as soon as the area changes
st.subheader("1. Where is it?")
all_df = db.load_listings()
c1, c2 = st.columns(2)
place = c1.selectbox("Area", listing_logic.area_names(), index=None, placeholder="Choose an area")
if place is None:
    st.info("Choose the area first. Then you will see nearby areas, schools and offices to check distances.")
    st.stop()

known = sorted({s for s in all_df[all_df.Place == place].Sub.dropna() if s not in ("", "Unknown")})
block_choice = c2.selectbox("Block / sub-area", [UNSURE] + known + [OTHER])
sub = "Unknown"
if block_choice == OTHER:
    typed = c2.text_input("Block / sub-area name", max_chars=60, placeholder="e.g. Block C or Section 10")
    sub = typed.strip() or "Unknown"
elif block_choice != UNSURE:
    sub = block_choice

st.markdown("**Nearby places** (straight-line distance, to help you choose)")
near = nearby.suggest(place, None if sub == "Unknown" else sub, k_areas=8, k_landmarks=12)
n1, n2 = st.columns(2)
with n1:
    st.caption("Nearby areas")
    if near["areas"]:
        ui.show_df(pd.DataFrame([{"Area": a["area"], "km": a["km"]} for a in near["areas"]]), hide_index=True)
    else:
        st.caption("None within 8 km.")
with n2:
    st.caption("Nearby schools, colleges, universities, offices")
    if near["landmarks"]:
        ui.show_df(pd.DataFrame([{"Place": x["name"], "Type": x["kind"], "km": x["km"]} for x in near["landmarks"]]),
                   hide_index=True)
    else:
        st.caption("No landmarks loaded nearby yet (run fetch_landmarks.py).")

options = {}
for a in near["areas"]:
    options[f"{a['area']} (area) · about {a['km']} km"] = (a["area"], a["lat"], a["lon"])
for x in near["landmarks"]:
    options[f"{x['name']} ({x['kind']}) · about {x['km']} km"] = (x["name"], x["lat"], x["lon"])
picked = st.multiselect("Check the road distance to (optional, up to 5)", list(options), max_selections=5)
if picked:
    use_net = st.checkbox("Use the internet for real road distance", value=True)
    if st.button("Show road distances"):
        rows = []
        for label in picked:
            name, la, lo = options[label]
            res = nearby.road_distance(place, sub, la, lo, use_network=use_net)
            if res:
                km, mn, src = res
                rows.append({"Place": name, "Road km": round(km, 1), "Minutes": round(mn),
                             "Source": "road route" if src in ("osrm", "google") else "straight-line estimate"})
        st.session_state["road_rows"] = rows
    if st.session_state.get("road_rows"):
        ui.show_df(pd.DataFrame(st.session_state["road_rows"]), hide_index=True)
        st.caption("Renters see these distances automatically when they search for a destination.")

# ---- step 2: the details
st.subheader("2. The flat")
with st.form("add_flat"):
    f1, f2, f3, f4 = st.columns(4)
    sqft = f1.number_input("Size (sqft)", min_value=0, max_value=20000, value=900, step=50)
    bed = f2.number_input("Bedrooms", min_value=0, max_value=20, value=2)
    bath = f3.number_input("Bathrooms", min_value=0, max_value=20, value=2)
    price = f4.number_input("Rent per month (৳)", min_value=0, max_value=2_000_000, value=20000, step=500)
    st.caption("Optional details help renters. Leave 'Not sure' if you do not know.")
    g1, g2, g3, g4 = st.columns(4)
    floor = g1.number_input("Floor", min_value=0, max_value=60, value=None, placeholder="Not sure")
    lift, gas = g2.selectbox("Lift", YN), g3.selectbox("Gas", YN)
    parking, generator = g4.selectbox("Parking", YN), g1.selectbox("Generator", YN)
    furnished = g2.selectbox("Furnished", YN)
    rule = g3.selectbox("Who may rent?", RULES, format_func=lambda k: listing_logic.TENANT_RULES.get(k, k))
    advance = g4.number_input("Advance (months of rent)", min_value=0.0, max_value=12.0, value=None,
                              placeholder="Not sure", step=0.5)
    available_from = None if paid else st.date_input("Available from", value=date.today())
    address = st.text_input("Street address (optional)", max_chars=200, placeholder="House, road, block")
    source_url = "" if paid else st.text_input("Link to the advert (optional)", max_chars=300)
    contact = st.text_input("Phone or email (optional)", max_chars=80)
    contact_public = st.checkbox("Show my contact to renters who find this flat", value=False, disabled=paid)
    consent = st.checkbox("I agree that the details above are stored and (if ticked) shown, as explained on the "
                          "About and privacy page.")
    submit = st.form_submit_button("Submit for review", type="primary")

if submit:
    fair = recommender.predict_fair_rent(place, sub, float(sqft), int(bed), int(bath))
    errors, flags = listing_logic.validate(place, float(sqft), int(bed), int(bath), float(price),
                                           listing_logic.area_names(), fair)
    if not consent:
        errors.append("Please tick the agreement box.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        dup = db.find_duplicate(place, sub, float(sqft), int(bed), int(bath), float(price))
        if dup:
            st.warning(f"A very similar flat (number {dup}) is already listed. If it is yours, use "
                       "'Manage my listing' to change it. Otherwise change a detail and submit again.")
        else:
            code = listing_logic.make_edit_code()
            rec = {"location": f"{sub}, {place}, Dhaka" if sub != "Unknown" else f"{place}, Dhaka",
                   "place": place, "sub": sub, "sqft": float(sqft), "bed": int(bed), "bath": int(bath),
                   "price": float(price), "fair_rent": round(fair, -2), "status": "pending",
                   "entry_kind": "paid_report" if paid else "available", "rent_type": "paid" if paid else "asking",
                   "edit_code_hash": listing_logic.hash_code(code), "flags": "; ".join(flags) or None,
                   "contact": contact.strip() or None,
                   "contact_public": int(bool(contact.strip()) and contact_public and not paid)}
            extras = {"floor": None if floor is None else int(floor), "lift": yn(lift), "gas": yn(gas),
                      "parking": yn(parking), "generator": yn(generator), "furnished": yn(furnished),
                      "tenant_rule": None if rule == "Not sure" else rule,
                      "advance_months": None if advance is None else float(advance),
                      "available_from": None if available_from is None else available_from.isoformat(),
                      "address": address.strip() or None, "source_url": source_url.strip() or None}
            rec.update({k: v for k, v in extras.items() if v is not None})
            new_id = db.add_listing(rec)
            st.success(f"Thank you! Your listing number is **{new_id}**. An admin will review it soon.")
            st.markdown("**Your private edit code (shown only once):**")
            st.code(code)
            st.warning("Write down the listing number and this code now. You need both to change the rent, confirm "
                       "the flat is still available, or mark it rented. We cannot recover the code.")
            if flags:
                st.info("Your rent is quite different from similar flats, so the admin will take a closer look "
                        "before it goes live. That is normal.")
