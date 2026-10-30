"""Dashboard: coverage per area, rent spread, owner activity, model accuracy."""
import json

import numpy as np
import pandas as pd
import streamlit as st

import auth
import coverage
import db
import permissions
import ui
from common import METRICS_PATH

ui.inject_css()
permissions.guard("dashboard")
ui.hero("Dashboard", "How many flats each area has, where the data is thin or old, and how well the rent model does.")

df = db.load_listings()
s = coverage.summary(df)
c = st.columns(5)
c[0].metric("Live flats", f"{s['live_total']:,}")
c[1].metric("Owner-listed (live)", f"{s['user_live']:,}")
c[2].metric("Waiting for review", f"{s['pending']:,}")
c[3].metric("Added in 7 days", f"{s['added_7d']:,}")
c[4].metric("Rented or expired", f"{s['rented_or_expired']:,}")

t_rev, t_cov, t_rent, t_model = st.tabs(["Reviews", "Coverage by area", "Rents", "Model accuracy"])

with t_rev:
    rs = db.review_stats()
    r1, r2, r3 = st.columns(3)
    r1.metric("People with an account", f"{db.count_users():,}")
    r2.metric("Reviews", f"{rs['count']:,}")
    r3.metric("Average rating", f"{rs['average']} / 5" if rs["average"] is not None else "-")
    reviews = db.latest_reviews(20)
    if not reviews:
        st.caption("No reviews yet. Write the first one from My account.")
    for r in reviews:
        who = auth.ROLE_LABELS.get(r["role"], "")
        st.markdown(f'<div class="review">{ui.stars(r["rating"])}<p>{ui.esc(r["comment"])}</p>'
                    f'<div class="by"><b>{ui.esc(r["name"])}</b>{" · " + ui.esc(who) if who else ""}'
                    f' · {ui.esc(r["created_at"])}</div></div>', unsafe_allow_html=True)
        st.write("")
    ui.link("views/account.py", "Write or edit my review", "⭐")

with t_cov:
    table = coverage.coverage_table(df)
    st.caption("Areas at the top most need new or fresher owner listings. 'Original listings' come from the "
               "old dataset and are not confirmed; 'User-listed' flats were added by owners and are confirmed.")
    pick = st.selectbox("Show", ["All areas", "Needs data", "Stale", "Needs update", "OK"])
    shown = table if pick == "All areas" else table[table.Status == pick]
    ui.show_df(shown, hide_index=True)
    if not table.empty:
        st.markdown("**Listings per area (top 25 by priority)**")
        st.bar_chart(table.head(25).set_index("Area")[["Original listings", "User-listed (live)"]])

with t_rent:
    d = df.copy()
    d["status"] = d.status.fillna("approved")
    live = d[(d.status == "approved") & (d.entry_kind.fillna("available") == "available")]
    st.markdown("**Median rent by area** (areas with at least 5 flats)")
    g = live.groupby("Place").Price.agg(["median", "size"])
    g = g[g["size"] >= 5].sort_values("median", ascending=False).head(30)
    if g.empty:
        st.caption("Not enough data yet.")
    else:
        st.bar_chart(g["median"])
    st.markdown("**Rent spread in one area**")
    area = st.selectbox("Area", sorted(live.Place.unique()))
    sub = live[live.Place == area].Price
    if len(sub) >= 5:
        counts, edges = np.histogram(sub, bins=min(12, max(4, len(sub) // 5)))
        labels = [f"{int(lo / 1000)}-{int(hi / 1000)}k" for lo, hi in zip(edges[:-1], edges[1:])]
        st.bar_chart(pd.DataFrame({"flats": counts}, index=labels))
        q = sub.quantile([.1, .5, .9])
        st.caption(f"Typical range: {ui.money(q[.1])} to {ui.money(q[.9])}, middle {ui.money(q[.5])} per month.")
    else:
        st.caption("Fewer than 5 flats in this area.")

with t_model:
    try:
        m = json.loads(METRICS_PATH.read_text())
        st.markdown(f"Best model: **{m['best']}** trained on {m['n_listings']:,} unique listings.")
        st.markdown("**Test on blocks it has never seen (the number to trust)**")
        ui.show_df(pd.DataFrame(m["block_holdout_metrics"]).T)
        st.markdown("**Random split (optimistic: same blocks in train and test)**")
        ui.show_df(pd.DataFrame(m["test_metrics"]).T)
    except Exception:
        st.caption("Run `python train.py` to see the comparison of models.")
    log = db.model_log_df()
    st.markdown("**Error on owner-listed flats the model never saw**")
    if log.empty:
        st.caption("Needs at least 10 approved owner-listed flats. The upkeep job logs a row each time the amount of data grows.")
    else:
        st.line_chart(log.set_index("id")[["mape"]])
        ui.show_df(log.tail(10), hide_index=True)
