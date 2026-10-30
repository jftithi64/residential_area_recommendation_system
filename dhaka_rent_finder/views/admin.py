"""Admin: review new entries, change status, run the upkeep job, import rows."""
import hmac
import os
import time

import pandas as pd
import streamlit as st

import db
import import_extra_listings
import maintenance
import ui

WEAK = {"", "admin123", "change-me", "password", "admin"}
TEMPLATE = ("location,sqft,bed,bath,price,tenant_rule,floor,lift,gas,parking,generator,furnished,available_from,"
            "source_url,address\n\"Block C, Mirpur 10, Mirpur, Dhaka\",900,2,2,18000,family,3,1,1,0,1,0,2026-11-01,,\n")

ui.inject_css()
ui.hero("Admin", "Review new entries, keep the data fresh, and import rows.")

password = os.environ.get("RENT_ADMIN_PASSWORD", "")
if password.strip().lower() in WEAK:
    st.error("The admin page is locked until you set your own password. Put it in the `.env` file as "
             "`RENT_ADMIN_PASSWORD=...` (VS Code run configs read it), or set the environment variable "
             "before starting the site. The default password is no longer accepted.")
    st.stop()

if not st.session_state.get("admin_ok"):
    if time.time() < st.session_state.get("admin_locked_until", 0):
        st.error("Too many wrong attempts. Wait a minute and try again.")
        st.stop()
    typed = st.text_input("Admin password", type="password")
    if st.button("Log in", type="primary"):
        if hmac.compare_digest(typed.encode(), password.encode()):
            st.session_state["admin_ok"] = True
            st.session_state["admin_fails"] = 0
            st.rerun()
        else:
            n = st.session_state.get("admin_fails", 0) + 1
            st.session_state["admin_fails"] = n
            if n >= 5:
                st.session_state["admin_locked_until"] = time.time() + 60
                st.session_state["admin_fails"] = 0
            st.error("Wrong password.")
    st.stop()

if st.button("Log out"):
    st.session_state["admin_ok"] = False
    st.rerun()

df = db.load_listings(include_private=True)
user = df[df.is_extra.fillna(0) == 1]
t_queue, t_all, t_upkeep, t_import, t_survey = st.tabs(
    ["Review queue", "All owner entries", "Upkeep job", "Import rows", "Survey"])

with t_queue:
    pending = user[user.status == "pending"].sort_values("listing_id")
    st.markdown(f"**{len(pending)} waiting for review**")
    for _, r in pending.iterrows():
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f"**#{int(r.listing_id)} · {r.Location}**")
            left.caption(f"{r.Sqft:.0f} sqft · {int(r.Bed)} bed · {int(r.Bath)} bath · rent {ui.money(r.Price)} · "
                         f"typical {ui.money(r.fair_rent)} · {r.entry_kind} · listed {r.listed_at}")
            if isinstance(r.flags, str) and r.flags:
                left.warning(f"Check: {r.flags}")
            extra = [f"{k}: {r[k]}" for k in ("address", "contact", "source_url", "tenant_rule") if pd.notna(r[k])]
            if extra:
                left.caption(" · ".join(extra))
            if right.button("Approve", key=f"ok{int(r.listing_id)}", type="primary"):
                db.set_status(int(r.listing_id), "approved")
                st.rerun()
            if right.button("Reject", key=f"no{int(r.listing_id)}"):
                db.set_status(int(r.listing_id), "rejected")
                st.rerun()

with t_all:
    status = st.selectbox("Status", ["all"] + db.STATUSES)
    shown = user if status == "all" else user[user.status == status]
    cols = ["listing_id", "Location", "Sqft", "Bed", "Bath", "Price", "fair_rent", "status", "entry_kind",
            "listed_at", "updated_at"]
    ui.show_df(shown[cols], hide_index=True)
    x1, x2, x3 = st.columns([1, 1, 1])
    lid = x1.number_input("Listing number", min_value=0, value=None, step=1, key="adm_id")
    new_status = x2.selectbox("Change status to", db.STATUSES, key="adm_status")
    if x3.button("Change status") and lid is not None:
        if int(lid) in set(user.listing_id.astype(int)):
            db.set_status(int(lid), new_status)
            st.success("Done.")
            st.rerun()
        else:
            st.error("No owner entry has that number.")

with t_upkeep:
    st.markdown("Imports new form rows (as pending), finds map positions, hides flats not confirmed for 45 days, "
                "and checks the rent model on approved owner flats.")
    net = st.checkbox("Use the internet (form download and address search)", value=False)
    if st.button("Run upkeep now"):
        with st.spinner("Working..."):
            res = maintenance.run_all(use_network=net)
        st.json(res)
    log = db.model_log_df()
    if not log.empty:
        ui.show_df(log.tail(10), hide_index=True)

with t_import:
    st.download_button("Download CSV template", TEMPLATE, file_name="extra_listings_template.csv", mime="text/csv")
    up = st.file_uploader("CSV file with real listings", type=["csv"])
    if up is not None:
        try:
            table = pd.read_csv(up)
            ui.show_df(table.head(20), hide_index=True)
            mode = st.radio("Import as", ["pending", "approved"], horizontal=True)
            if st.button("Import these rows"):
                added, skipped = import_extra_listings.import_rows(table, status=mode)
                st.success(f"Added {len(added)} listings as {mode}.")
                for s in skipped:
                    st.warning(s)
        except Exception as e:
            st.error(f"Could not import: {e}")

with t_survey:
    pairs = db.pairs_df()
    if pairs.empty:
        st.caption("No survey answers yet.")
    else:
        real = pairs[pairs.synthetic == 0]
        st.metric("Real answers", len(real))
        st.metric("People", real.person_id.nunique())
        st.caption("When there are at least 60 answers from 8 people, run `python train_ranker.py`.")
