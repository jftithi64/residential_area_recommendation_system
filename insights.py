"""Numbers for the admin Insights page: sign-ups, listed flats, review queue, and what people say they want.

Pure functions that return numbers or DataFrames, so they can be tested without a browser.
Sign-ups count renter and owner accounts only (the administrator account is left out).
"""
import json
from datetime import date, datetime, timedelta

import pandas as pd

import auth
import db


def users_df():
    """One row per renter / owner account: user_id, role, created_at, last_login, email_verified."""
    with auth._connect() as con:
        rows = con.execute("SELECT user_id, role, created_at, last_login, email_verified FROM users "
                           "WHERE role IN ('renter','owner')").fetchall()
    df = pd.DataFrame(rows, columns=["user_id", "role", "created_at", "last_login", "email_verified"])
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["last_login"] = pd.to_datetime(df["last_login"], errors="coerce")
    return df


def daily_counts(values, days=30, today=None):
    """Counts per day for the last `days` days, zero-filled. values: dates or date strings. Returns a 1-column frame."""
    today = today or date.today()
    idx = pd.date_range(today - timedelta(days=days - 1), today)
    s = pd.to_datetime(pd.Series(list(values), dtype="object"), errors="coerce").dropna()
    counts = s.dt.normalize().value_counts() if len(s) else pd.Series(dtype=int)
    return counts.reindex(idx, fill_value=0).sort_index().rename("count").to_frame()


def owner_listings():
    """Flats added by people (not the public dataset), all statuses."""
    df = db.load_listings()
    return df[df.is_extra.fillna(0) == 1].copy()


def signup_summary(today=None):
    today = today or date.today()
    u = users_df()
    cut7, cut30 = pd.Timestamp(today - timedelta(days=6)), pd.Timestamp(today - timedelta(days=29))
    return {
        "total": len(u),
        "renters": int((u.role == "renter").sum()),
        "owners": int((u.role == "owner").sum()),
        "last7": int((u.created_at >= cut7).sum()),
        "last30": int((u.created_at >= cut30).sum()),
        "verified": int((u.email_verified == 1).sum()),
        "active7": int((u.last_login >= cut7).sum()),
    }


def listing_summary(today=None):
    today = today or date.today()
    d = owner_listings()
    listed = pd.to_datetime(d.listed_at, errors="coerce")
    status = d.status.fillna("approved")
    return {
        "total": len(d),
        "live": int(((status == "approved") & (d.entry_kind.fillna("available") == "available")).sum()),
        "pending": int((status == "pending").sum()),
        "rejected": int((status == "rejected").sum()),
        "rented": int((status == "rented").sum()),
        "last7": int((listed >= pd.Timestamp(today - timedelta(days=6))).sum()),
    }


def status_counts():
    d = owner_listings()
    return d.status.fillna("approved").value_counts().reindex(db.STATUSES, fill_value=0).rename("flats").to_frame()


def listings_by_area(top=15):
    d = owner_listings()
    live = d[d.status.fillna("approved") == "approved"]
    return live.Place.value_counts().head(top).rename("flats").to_frame()


def review_stats(today=None):
    """The admin's review work: how many wait, how old the oldest is, and how many entries were turned down."""
    today = today or date.today()
    d = owner_listings()
    status = d.status.fillna("approved")
    waiting = d[status == "pending"]
    oldest = None
    if len(waiting):
        dates = pd.to_datetime(waiting.listed_at, errors="coerce").dropna()
        if len(dates):
            oldest = max(0, (pd.Timestamp(today) - dates.min()).days)
    reviewed = int((status != "pending").sum())
    rejected = int((status == "rejected").sum())
    return {"waiting": len(waiting), "oldest_days": oldest, "reviewed": reviewed, "rejected": rejected,
            "rejected_pct": round(100 * rejected / reviewed) if reviewed else None}


def interests_df():
    with auth._connect() as con:
        rows = con.execute("SELECT i.user_id, u.role, i.purposes, i.areas, i.bedrooms, i.budget_max "
                           "FROM user_interests i JOIN users u ON u.user_id=i.user_id "
                           "WHERE u.role IN ('renter','owner')").fetchall()
    return pd.DataFrame(rows, columns=["user_id", "role", "purposes", "areas", "bedrooms", "budget_max"])


def interest_summary():
    """What people said they want at sign-up: purposes, areas, bedrooms and budget bands."""
    d = interests_df()
    empty = pd.DataFrame({"people": []})
    if d.empty:
        return {"people": 0, "purposes": empty, "areas": empty, "bedrooms": empty, "budget": empty}

    def tally(col):
        items = [x for cell in d[col] for x in json.loads(cell or "[]")]
        return pd.Series(items, dtype="object").value_counts().rename("people").to_frame()

    bands = pd.cut(d.budget_max.dropna(), [0, 10_000, 20_000, 30_000, 50_000, 500_000],
                   labels=["up to 10k", "10-20k", "20-30k", "30-50k", "above 50k"])
    return {"people": len(d), "purposes": tally("purposes"), "areas": tally("areas").head(15),
            "bedrooms": d.bedrooms.dropna().astype(int).value_counts().sort_index().rename("people").to_frame(),
            "budget": bands.value_counts().sort_index().rename("people").to_frame()}


def demand_vs_supply(top=15):
    """Areas people want (sign-up interests) next to live owner-listed flats there: where more listings are needed."""
    want = interest_summary()["areas"].rename(columns={"people": "interested people"})
    have = listings_by_area(top=500).rename(columns={"flats": "live owner flats"})
    out = want.join(have, how="left").fillna(0).astype(int)
    return out.sort_values("interested people", ascending=False).head(top)
