"""Manage my listing: change the rent, confirm it is still available, mark rented, remove."""
import time

import streamlit as st

import db
import listing_logic
import recommender
import permissions
import ui

MAX_FAILS, WINDOW = 5, 900   # five wrong codes per listing in 15 minutes locks it for the rest of the window
STATUS_TEXT = {
    "pending": "Waiting for admin review. It is not shown to renters yet.",
    "approved": "Live. Renters can find it.",
    "rented": "Marked as rented. It is hidden from renters.",
    "expired": "Hidden because it was not confirmed for 45 days. Press 'Still available' to show it again.",
    "removed": "Removed.",
    "rejected": "The admin did not accept this entry.",
}


@st.cache_resource
def _fails():
    return {}


def locked(listing_id):
    count, first = _fails().get(listing_id, (0, 0.0))
    if time.time() - first > WINDOW:
        _fails().pop(listing_id, None)
        return False
    return count >= MAX_FAILS


def record_fail(listing_id):
    count, first = _fails().get(listing_id, (0, time.time()))
    _fails()[listing_id] = (count + 1, first)


ui.inject_css()
permissions.guard("my_listing")
ui.hero("Manage my listing", "Use the listing number and private edit code you received when you added the flat.")

if "owned" not in st.session_state:
    c1, c2 = st.columns(2)
    num = c1.number_input("Listing number", min_value=0, value=None, step=1, placeholder="e.g. 1000012")
    code = c2.text_input("Edit code", type="password")
    if st.button("Open my listing", type="primary"):
        bad = "The listing number or code is not right."
        if num is None or not code:
            st.error("Enter both the listing number and the code.")
        elif locked(int(num)):
            st.error("Too many wrong attempts. Please try again in 15 minutes.")
        else:
            row = db.get_listing(int(num))
            if row and row.get("is_extra") == 1 and listing_logic.check_code(code, row.get("edit_code_hash")):
                st.session_state["owned"] = int(num)
                st.rerun()
            else:
                record_fail(int(num))
                st.error(bad)
    st.stop()

listing_id = st.session_state["owned"]
row = db.get_listing(listing_id)
if not row:
    st.session_state.pop("owned", None)
    st.error("That listing no longer exists.")
    st.stop()

top = st.columns([4, 1])
top[0].subheader(f"Listing {listing_id}: {row['location']}")
if top[1].button("Close"):
    st.session_state.pop("owned", None)
    st.rerun()
st.info(f"**Status: {row['status']}.** {STATUS_TEXT.get(row['status'], '')}")
st.caption(f"{row['sqft']:.0f} sqft · {row['bed']} bed · {row['bath']} bath · rent {ui.money(row['price'])} · "
           f"last confirmed {row.get('updated_at') or row.get('listed_at')}")
if row.get("flags"):
    st.caption(f"Held for review: {row['flags']}")

st.markdown("#### Change the rent")
new_rent = st.number_input("Rent per month (৳)", min_value=0, value=int(row["price"]), step=500)
if st.button("Save new rent"):
    fair = recommender.predict_fair_rent(row["place"], row["sub"], row["sqft"], int(row["bed"]), int(row["bath"]))
    errors, flags = listing_logic.validate(row["place"], row["sqft"], int(row["bed"]), int(row["bath"]),
                                           float(new_rent), listing_logic.area_names(), fair)
    if errors:
        for e in errors:
            st.error(e)
    else:
        fields = {"price": float(new_rent), "fair_rent": round(fair, -2), "flags": "; ".join(flags) or None}
        if flags and row["status"] == "approved":
            fields["status"] = "pending"
            st.warning("This rent is far from similar flats, so the admin will check it again before it shows.")
        db.update_listing(listing_id, **fields)
        st.success("Rent updated.")
        st.rerun()

st.markdown("#### Availability")
a, b, c = st.columns(3)
if a.button("Still available (confirm)"):
    db.update_listing(listing_id, status="approved" if row["status"] in ("approved", "expired") else row["status"])
    st.success("Thanks. The 45-day clock restarted.")
    st.rerun()
if b.button("Mark as rented"):
    db.set_status(listing_id, "rented")
    st.success("Marked as rented. Congratulations!")
    st.rerun()
with c:
    sure = st.checkbox("I want to remove this listing")
    if st.button("Remove listing", disabled=not sure):
        db.set_status(listing_id, "removed")
        st.success("Removed.")
        st.rerun()

st.markdown("#### Contact visibility")
has_contact = bool(row.get("contact"))
show = st.checkbox("Show my contact to renters", value=bool(row.get("contact_public")), disabled=not has_contact)
if has_contact and st.button("Save contact setting"):
    db.update_listing(listing_id, touch=False, contact_public=int(show))
    st.success("Saved.")
    st.rerun()
if not has_contact:
    st.caption("You did not add a contact, so nothing is shown to renters.")
