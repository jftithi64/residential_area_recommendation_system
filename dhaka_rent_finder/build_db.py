"""Create / refresh data/rent.db from the cleaned listings and the landmark list.

Run:  python build_db.py          (safe to re-run: keeps owner listings, survey answers and geocoded coordinates)
      python build_db.py --reset  (delete the database first)
      python build_db.py --demo-addresses      (DEMO ONLY: add made-up placeholder addresses to dataset rows)
Needs data/listings_clean.csv, which `python train.py` creates.
"""
import sys

import pandas as pd

import db
import make_demo_addresses
from common import AREA_COORDS, DATA_CLEAN, ROOT


def main():
    if "--reset" in sys.argv and db.DB_PATH.exists():
        db.DB_PATH.unlink()
    if not DATA_CLEAN.exists():
        sys.exit("data/listings_clean.csv not found - run `python train.py` first.")

    listings = pd.read_csv(DATA_CLEAN)
    lm = pd.read_csv(ROOT / "data" / "landmarks.csv")
    missing = lm["lat"].isna()
    for i in lm.index[missing]:  # schools whose exact point is unknown use their area centre
        la, lo = AREA_COORDS.get(lm.at[i, "area"], (None, None))
        lm.at[i, "lat"], lm.at[i, "lon"] = la, lo

    with db.connect() as con:
        con.execute("DELETE FROM listings WHERE is_extra=0")  # keeps flats added by import_extra_listings.py
        con.executemany(
            "INSERT INTO listings(listing_id, location, place, sub, sqft, bed, bath, price, fair_rent, dup_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(int(r.listing_id), r.Location, r.Place, r.Sub, float(r.Sqft), int(r.Bed), int(r.Bath),
              float(r.Price), float(r.fair_rent), int(r.dup_count)) for r in listings.itertuples()])
        for r in lm.itertuples():
            if pd.isna(r.lat):
                continue
            con.execute("INSERT INTO landmarks(name, kind, area, lat, lon, coord_source) VALUES (?,?,?,?,?,?) "
                        "ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, area=excluded.area, "
                        "lat=CASE WHEN landmarks.coord_source='osm' THEN landmarks.lat ELSE excluded.lat END, "
                        "lon=CASE WHEN landmarks.coord_source='osm' THEN landmarks.lon ELSE excluded.lon END, "
                        "coord_source=CASE WHEN landmarks.coord_source='osm' THEN 'osm' ELSE excluded.coord_source END",
                        (r.name, r.kind, r.area, float(r.lat), float(r.lon), r.coord_source))
        for place, (la, lo) in AREA_COORDS.items():
            con.execute("INSERT OR IGNORE INTO location_coords VALUES (?,?,?,?,?)",
                        (place, "", la, lo, "manual_centroid"))
            # every area can also be a destination (for office workers); an OSM point wins if it is already there
            con.execute("INSERT OR IGNORE INTO landmarks(name, kind, area, lat, lon, coord_source) VALUES (?,?,?,?,?,?)",
                        (place, "area", place, la, lo, "manual_centroid"))
        demo = make_demo_addresses.apply(con) if "--demo-addresses" in sys.argv else 0   # off by default
        n = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        k = con.execute("SELECT kind, COUNT(*) FROM landmarks GROUP BY kind").fetchall()
    print(f"Database ready: {n} listings; landmarks by type: {dict(k)}")
    if demo:
        print(f"Added made-up demo addresses to {demo} dataset rows (shown as '[demo address]' in the app).")
    print("Tip: run `python geocode_places.py` once (internet needed) to replace approximate "
          "coordinates with OpenStreetMap ones.")


if __name__ == "__main__":
    main()
