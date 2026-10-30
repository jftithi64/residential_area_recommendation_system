"""Coverage of the listing database per area: where is data thin, old or incomplete?

An area "needs an update" when it has no recently listed flats from users, too few of them, only old ones, or
user-listed flats that miss important details (floor, lift, gas, tenant rule).
"""
from datetime import date

import numpy as np
import pandas as pd

STALE_DAYS = 45
MIN_USER = 5
DETAIL_COLS = ["floor", "lift", "gas", "tenant_rule"]


def _user_mask(df):
    return (df.is_extra == 1) & (df.status == "approved") & (df.entry_kind.fillna("available") == "available")


def coverage_table(df, stale_days=STALE_DAYS, min_user=MIN_USER, today=None):
    """One row per area, sorted so the areas most worth collecting next come first."""
    today = pd.Timestamp(today or date.today())
    df = df.copy()
    df["status"] = df.status.fillna("approved")
    df["is_extra"] = df.is_extra.fillna(0)
    original = df[df.is_extra == 0]
    user = df[_user_mask(df)]
    pending = df[(df.is_extra == 1) & (df.status == "pending")]
    live = df[(df.status == "approved") & (df.entry_kind.fillna("available") == "available")]

    rows = []
    for place in sorted(df.Place.unique()):
        u = user[user.Place == place]
        n_orig = int((original.Place == place).sum())
        newest = pd.to_datetime(u.updated_at.fillna(u.listed_at), errors="coerce").max() if len(u) else pd.NaT
        days = int((today - newest).days) if pd.notna(newest) else None
        missing = float(u[DETAIL_COLS].isna().any(axis=1).mean() * 100) if len(u) else np.nan
        reasons = []
        if len(u) == 0:
            reasons.append("no user-listed flats yet")
        elif len(u) < min_user:
            reasons.append(f"only {len(u)} user-listed flats")
        if days is not None and days > stale_days:
            reasons.append(f"newest listing is {days} days old")
        if len(u) and missing > 50:
            reasons.append(f"{missing:.0f}% of listings miss details")
        status = "OK"
        if reasons:
            status = "Needs data" if len(u) == 0 else ("Stale" if days is not None and days > stale_days else "Needs update")
        priority = n_orig / (1 + len(u)) + (days / stale_days if days is not None else 0)
        rows.append({"Area": place, "Original listings": n_orig, "User-listed (live)": int(len(u)),
                     "Waiting for review": int((pending.Place == place).sum()),
                     "Newest user listing": newest.date().isoformat() if pd.notna(newest) else "",
                     "Days since newest": days, "Missing details (%)": None if np.isnan(missing) else round(missing),
                     "Median rent (৳)": float(live[live.Place == place].Price.median()),
                     "Status": status, "Why": "; ".join(reasons), "Priority": round(priority, 1)})
    out = pd.DataFrame(rows)
    return out.sort_values("Priority", ascending=False).reset_index(drop=True)


def summary(df, today=None):
    """Headline numbers for the dashboard."""
    today = pd.Timestamp(today or date.today())
    df = df.copy()
    df["status"] = df.status.fillna("approved")
    df["is_extra"] = df.is_extra.fillna(0)
    live = df[(df.status == "approved") & (df.entry_kind.fillna("available") == "available")]
    user = df[_user_mask(df)]
    listed = pd.to_datetime(user.listed_at, errors="coerce")
    return {
        "live_total": int(len(live)),
        "original": int((live.is_extra == 0).sum()),
        "user_live": int(len(user)),
        "pending": int(((df.is_extra == 1) & (df.status == "pending")).sum()),
        "rented_or_expired": int(((df.is_extra == 1) & df.status.isin(["rented", "expired"])).sum()),
        "paid_reports": int(((df.is_extra == 1) & (df.entry_kind == "paid_report") & (df.status == "approved")).sum()),
        "added_7d": int((listed >= today - pd.Timedelta(days=7)).sum()),
        "added_30d": int((listed >= today - pd.Timedelta(days=30)).sum()),
        "areas": int(live.Place.nunique()),
    }
