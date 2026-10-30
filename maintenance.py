"""Automatic upkeep of the listing database. Run it on a schedule (see README) or from the Admin page.

Run:  python maintenance.py                 do everything below
      python maintenance.py --no-network    skip the steps that need the internet

Steps
  1. import     new rows from the form export (data/form_responses.csv, or the web address in the
                FORM_CSV_URL environment variable, e.g. a Google Sheet published as CSV). New rows wait
                for admin review (status 'pending').
  2. geocode    find exact map positions for user-added flats that have an address but no position.
  3. expire     hide approved user-added flats not confirmed for 45 days.
  4. evaluate   test the rent model on approved user-added flats it has never seen and log the error.
"""
import os
import sys
import time

import numpy as np
import pandas as pd

import db
import import_extra_listings
import listing_logic
import maps
import recommender
from common import ROOT, add_features, split_location

FORM_CSV = ROOT / "data" / "form_responses.csv"


def import_form(use_network=True):
    """Import new form rows as pending. Returns (added, skipped, note)."""
    url = os.environ.get("FORM_CSV_URL")
    if url and use_network:
        try:
            import requests
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            FORM_CSV.write_bytes(r.content)
        except Exception as e:
            return 0, [], f"could not download the form export ({e.__class__.__name__})"
    if not FORM_CSV.exists():
        return 0, [], "no form export found (data/form_responses.csv)"
    added, skipped = import_extra_listings.import_rows(pd.read_csv(FORM_CSV), status="pending", dedupe=True)
    return len(added), skipped, ""


def geocode_missing(limit=50, use_network=True):
    """Add exact positions to user-added flats that have an address. Returns the number updated."""
    if not use_network:
        return 0
    df = db.load_listings()
    todo = df[(df.is_extra == 1) & df.exact_lat.isna() & df.address.notna() & (df.address.str.strip() != "")]
    n = 0
    for _, r in todo.head(limit).iterrows():
        parts = [r.address, r.Sub if r.Sub != "Unknown" else "", r.Place, "Dhaka"]
        hits = maps.geocode(", ".join(p for p in parts if p))
        if hits:
            db.update_listing(r.listing_id, touch=False, lat=hits[0]["lat"], lon=hits[0]["lon"])
            n += 1
        time.sleep(1.1)   # Nominatim allows about one request per second
    return n


def expire_old(days=listing_logic.STALE_DAYS):
    """Hide approved user-added flats that were not confirmed within `days`. Returns the number expired."""
    with db.connect() as con:
        cur = con.execute(
            "UPDATE listings SET status='expired' WHERE is_extra=1 AND status='approved' AND entry_kind='available' "
            "AND date(COALESCE(updated_at, listed_at)) < date('now', ?)", (f"-{int(days)} days",))
        return cur.rowcount


def evaluate_model(min_n=10):
    """Error of the rent model on approved user-added flats. Returns the metrics dict, or None if too few flats."""
    df = db.load_listings()
    d = df[(df.is_extra == 1) & (df.status == "approved")].dropna(subset=["Price", "Sqft", "Bed", "Bath"])
    if len(d) < min_n:
        return None
    X = add_features(pd.DataFrame({"Place": d.Place, "Sub": d.Sub.fillna("Unknown"), "Sqft": d.Sqft,
                                   "Bed": d.Bed, "Bath": d.Bath}))
    pred = np.expm1(recommender.load_model().predict(X[recommender.FEATURES]))
    err = np.abs(pred - d.Price.values)
    m = {"n": int(len(d)), "mae": float(err.mean()), "mape": float((err / d.Price.values).mean() * 100),
         "within20": float(((err / d.Price.values) <= 0.2).mean() * 100)}
    n_paid = int((d.rent_type == "paid").sum())
    last = db.model_log_df()
    if last.empty or int(last.n.iloc[-1]) != m["n"]:   # one row per new data size, not one per nightly run
        db.add_model_log(m["n"], m["mae"], m["mape"], m["within20"],
                         f"{n_paid} paid rents, {m['n'] - n_paid} asking rents")
    return m


def run_all(use_network=True):
    added, skipped, note = import_form(use_network)
    out = {"imported": added, "import_note": note, "import_skipped": len(skipped),
           "geocoded": geocode_missing(use_network=use_network), "expired": expire_old(),
           "model_check": evaluate_model()}
    return out


if __name__ == "__main__":
    res = run_all(use_network="--no-network" not in sys.argv)
    print("imported:", res["imported"], res["import_note"], "| skipped:", res["import_skipped"])
    print("geocoded:", res["geocoded"], "| expired:", res["expired"])
    m = res["model_check"]
    print("model check:", "not enough approved user-added flats yet (need 10)" if m is None else
          f"{m['n']} flats, average error ৳{m['mae']:,.0f} ({m['mape']:.1f}%), {m['within20']:.0f}% within 20%")
