"""Add REAL listings that carry the details the original dataset lacks.

Run:  python import_extra_listings.py my_listings.csv            (rows are approved straight away)
      python import_extra_listings.py my_listings.csv --pending  (rows wait for admin review)
      (copy data/extra_listings_template.csv, replace the example row with real adverts)

Columns
  location        e.g. "Block C, Mirpur 10, Mirpur, Dhaka" (same style as the dataset: block, area, Dhaka)
  sqft, bed, bath, price   numbers (price in BDT per month)
  tenant_rule     family | bachelor_male | bachelor_female | any   (blank = unknown)
  floor, lift, gas, parking, generator, furnished   numbers; yes/no as 1 or 0 (blank = unknown)
  available_from  date text, e.g. 2026-11-01
  source_url      link to the original advert so a person can check it
  address, lat, lon          optional street address and exact map position
  advance_months, rent_type  optional; rent_type is asking or paid
  entry_kind      available (default) or paid_report (a rent someone actually pays; never recommended)

Each row is stored with is_extra=1 and gets the ML fair-rent estimate. Rows survive build_db.py.
"""
import hashlib
import sys

import pandas as pd

import db
from common import split_location
from recommender import predict_fair_rent

OPTIONAL_INT = ["floor", "lift", "gas", "parking", "generator", "furnished"]
OPTIONAL_TEXT = ["available_from", "source_url", "address", "rent_type", "entry_kind"]
OPTIONAL_FLOAT = ["lat", "lon", "advance_months"]


def _clean(v):
    return None if pd.isna(v) else v


def row_hash(row):
    return hashlib.sha256("|".join(str(v) for v in row.values).encode("utf-8")).hexdigest()


def import_rows(df, status="approved", dedupe=False):
    """Add rows from a DataFrame. Returns (added_ids, skipped_messages)."""
    need = {"location", "sqft", "bed", "bath", "price"}
    if not need <= set(df.columns):
        raise ValueError(f"Missing columns: {sorted(need - set(df.columns))}")
    coords = db.location_coords()
    added, skipped = [], []
    for _, r in df.iterrows():
        h = row_hash(r)
        if dedupe:
            with db.connect() as con:
                if con.execute("SELECT 1 FROM imports WHERE row_hash=?", (h,)).fetchone():
                    continue
        place, sub = split_location(r["location"])
        if not isinstance(place, str) or (place, "") not in coords:
            skipped.append(f"area not recognised: {r['location']}")
            continue
        fair = predict_fair_rent(place, sub, float(r["sqft"]), int(r["bed"]), int(r["bath"]))
        rec = {"location": r["location"], "place": place, "sub": sub, "sqft": float(r["sqft"]), "bed": int(r["bed"]),
               "bath": int(r["bath"]), "price": float(r["price"]), "fair_rent": round(fair, -2), "status": status,
               "tenant_rule": _clean(r.get("tenant_rule"))}
        for k in OPTIONAL_INT:
            v = _clean(r.get(k))
            if v is not None:
                rec[k] = int(v)
        for k in OPTIONAL_FLOAT:
            v = _clean(r.get(k))
            if v is not None:
                rec[k] = float(v)
        for k in OPTIONAL_TEXT:
            v = _clean(r.get(k))
            if v is not None:
                rec[k] = str(v)
        added.append(db.add_listing(rec))
        if dedupe:
            with db.connect() as con:
                con.execute("INSERT OR IGNORE INTO imports(row_hash) VALUES (?)", (h,))
    return added, skipped


def main(path, status):
    added, skipped = import_rows(pd.read_csv(path), status=status)
    for s in skipped:
        print("skipped:", s)
    print(f"Added {len(added)} listings with status '{status}'.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], "pending" if "--pending" in sys.argv else "approved")
