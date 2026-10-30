"""Add well-known offices (companies, banks, government bodies) as destinations.

Edit data/extra_offices.csv (columns: name, area, lat, lon) and run:   python add_offices.py
  - area must be one of the area names in common.AREA_COORDS (e.g. Motijheel, Gulshan, Agargaon).
  - lat / lon are optional. Leave them empty and the office is placed at the centre of its area;
    fill them in (right-click the place in Google Maps and copy the numbers) for an exact point.
It adds the offices to data/landmarks.csv (so build_db.py keeps them) and to the running database.
Names that already exist are skipped. Restart the app (or wait 10 minutes) to see them in the search list.
"""
import pandas as pd

import db
from common import AREA_COORDS, ROOT

LM = ROOT / "data" / "landmarks.csv"
EXTRA = ROOT / "data" / "extra_offices.csv"


def main():
    extra = pd.read_csv(EXTRA)
    lm = pd.read_csv(LM)
    have = set(lm["name"].str.strip().str.lower())
    rows, added, skipped = [], [], []
    for r in extra.itertuples():
        name = str(r.name).strip()
        if name.lower() in have:
            skipped.append(f"{name} (already there)")
            continue
        if r.area not in AREA_COORDS:
            skipped.append(f"{name} (unknown area '{r.area}')")
            continue
        lat, lon = (r.lat, r.lon) if pd.notna(r.lat) and pd.notna(r.lon) else AREA_COORDS[r.area]
        exact = pd.notna(r.lat) and pd.notna(r.lon)
        rows.append({"name": name, "kind": "office", "area": r.area, "lat": float(lat), "lon": float(lon),
                     "coord_source": "manual_exact" if exact else "manual_area"})
        have.add(name.lower())
        added.append(name)
    if rows:
        pd.concat([lm, pd.DataFrame(rows)], ignore_index=True).to_csv(LM, index=False)
        with db.connect() as con:
            for x in rows:
                con.execute("INSERT OR IGNORE INTO landmarks(name, kind, area, lat, lon, coord_source) VALUES (?,?,?,?,?,?)",
                            (x["name"], x["kind"], x["area"], x["lat"], x["lon"], x["coord_source"]))
    print(f"Added {len(added)} offices.")
    for s in skipped:
        print("  skipped:", s)


if __name__ == "__main__":
    main()
