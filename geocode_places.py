"""One-time job: replace approximate coordinates with OpenStreetMap coordinates.

Run:  python geocode_places.py            (needs internet; about 12-15 minutes)
      python geocode_places.py --landmarks-only   (about 1 minute)

It looks up (1) every school/college/university in the landmark list and (2) every block /
sub-area that appears in the listings, e.g. "Block H, Bashundhara R-A, Dhaka". Results are saved
in data/rent.db, and anything not found keeps its area-centre coordinates. Nominatim's usage
policy allows at most 1 request per second, so this script waits between requests.
It can be stopped and re-run: finished items are skipped.
"""
import sys
import time

import db
import maps

DELAY = 1.1


def main():
    landmarks_only = "--landmarks-only" in sys.argv
    with db.connect() as con:
        lms = con.execute("SELECT landmark_id, name, area, coord_source FROM landmarks").fetchall()
    for lid, name, area, src in lms:
        if src == "osm":
            continue
        hits = maps.geocode(f"{name}, {area}, Dhaka")
        time.sleep(DELAY)
        if hits:
            with db.connect() as con:
                con.execute("UPDATE landmarks SET lat=?, lon=?, coord_source='osm' WHERE landmark_id=?",
                            (hits[0]["lat"], hits[0]["lon"], lid))
            print("landmark OK  :", name, hits[0]["lat"], hits[0]["lon"])
        else:
            print("landmark MISS:", name, "(kept approximate position)")
    if landmarks_only:
        return

    listings = db.load_listings()
    pairs = sorted(set(zip(listings.Place, listings.Sub)))
    pairs = [(p, s) for p, s in pairs if s not in ("", "Unknown")]
    with db.connect() as con:
        done = {(p, s) for p, s in con.execute("SELECT place, sub FROM location_coords WHERE source='osm'")}
    todo = [x for x in pairs if x not in done]
    print(f"{len(todo)} blocks/sub-areas to look up (about {len(todo) * DELAY / 60:.0f} minutes)")
    for i, (place, sub) in enumerate(todo, 1):
        hits = maps.geocode(f"{sub}, {place}, Dhaka")
        time.sleep(DELAY)
        if hits:
            with db.connect() as con:
                con.execute("INSERT OR REPLACE INTO location_coords VALUES (?,?,?,?,'osm')",
                            (place, sub, hits[0]["lat"], hits[0]["lon"]))
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} done")
    print("Finished. Old cached distances for moved points are replaced automatically on the next search.")


if __name__ == "__main__":
    main()
