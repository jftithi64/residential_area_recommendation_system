"""Download every school, college, university, office and neighbourhood in Dhaka from OpenStreetMap
and merge them into data/landmarks.csv (the file build_db.py reads).

Run:  python fetch_landmarks.py        (needs internet, takes 1-3 minutes)
      python build_db.py               (then load them into the database)

Kinds written: school, college, university, office, area
  - 'area' rows are neighbourhoods, so an office worker can pick ANY area of Dhaka as the destination.
  - Existing rows in data/landmarks.csv are kept (your curated points win); only new names are added.
  - A backup of the old file is saved as data/landmarks.backup.csv.
Downloads are cached in data/osm_cache/; delete that folder to fetch fresh data.
Names that appear many times ("Government Primary School") get the area added: "Name (Area)".
OpenStreetMap coverage is good but not perfect; anything missing can be added to landmarks.csv by hand.
Map data (c) OpenStreetMap contributors (ODbL).
"""
import json
import shutil
import time

import numpy as np
import pandas as pd
import requests

from common import AREA_COORDS, ROOT

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.private.coffee/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
CACHE = ROOT / "data" / "osm_cache"   # one json per kind, so a re-run skips what is already downloaded
BBOX = "23.62,90.25,23.95,90.55"   # south, west, north, east: Dhaka and its close surroundings
HEADERS = {"User-Agent": "dhaka-rent-prototype/0.1 (university student project)"}
TAGS = {
    "school": '["amenity"="school"]',
    "college": '["amenity"="college"]',
    "university": '["amenity"="university"]',
    "office": '["office"]',
    "area": '["place"~"^(suburb|neighbourhood|quarter)$"]',
}
LM_PATH = ROOT / "data" / "landmarks.csv"
COLS = ["name", "kind", "area", "lat", "lon", "coord_source"]


def run_query(tag):
    """Ask the free Overpass servers; they are often busy, so wait and retry on every mirror. None if all fail."""
    q = f'[out:json][timeout:120];nwr{tag}["name"]({BBOX});out center tags;'
    last = None
    for attempt in range(4):
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=150)
                r.raise_for_status()
                return r.json()["elements"]
            except Exception as e:
                last = e
                print(f"   {url.split('/')[2]} failed ({e.__class__.__name__}), trying the next server...")
                time.sleep(3)
        wait = 15 * (attempt + 1)
        print(f"   all servers busy, waiting {wait}s (round {attempt + 1}/4)")
        time.sleep(wait)
    print(f"   giving up for now: {last}")
    return None


def get_elements(kind, tag):
    """Cached download for one kind."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{kind}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    els = run_query(tag)
    if els is not None:
        f.write_text(json.dumps(els), encoding="utf-8")
    return els


def to_rows(kind, elements):
    rows = []
    for el in elements:
        t = el.get("tags", {})
        name = (t.get("name:en") or t.get("name") or "").strip()
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if name and lat and lon:
            rows.append({"name": name, "kind": kind, "area": t.get("addr:suburb", ""),
                         "lat": float(lat), "lon": float(lon), "coord_source": "osm"})
    return pd.DataFrame(rows, columns=COLS)


def nearest_area(lat, lon, names, pts):
    """Name of the closest known area centre (vectorised haversine)."""
    la1, lo1 = np.radians(lat), np.radians(lon)
    la2, lo2 = np.radians(pts[:, 0]), np.radians(pts[:, 1])
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return names[int(np.argmin(h))]


def main():
    frames, failed = {}, []
    for kind, tag in TAGS.items():
        els = get_elements(kind, tag)
        if els is None:
            failed.append(kind)
            continue
        frames[kind] = to_rows(kind, els)
        print(f"{kind:11s} {len(frames[kind])} found")
        time.sleep(3)
    if failed:
        print(f"\nCould not download: {', '.join(failed)}. Wait a few minutes and run the script again;"
              " the kinds already downloaded are kept and will not be fetched twice.")
        if "area" in failed or not frames:
            raise SystemExit(1)

    # area centres = the project's own list + every OSM neighbourhood
    centres = dict(AREA_COORDS)
    for r in frames.get("area", pd.DataFrame(columns=COLS)).itertuples():
        centres.setdefault(r.name, (r.lat, r.lon))
    names = np.array(list(centres))
    pts = np.array(list(centres.values()), dtype=float)

    new = pd.concat(frames.values(), ignore_index=True)
    blank = new["area"].str.strip() == ""
    new.loc[blank, "area"] = [nearest_area(la, lo, names, pts) for la, lo in zip(new.lat[blank], new.lon[blank])]
    new.loc[new.kind == "area", "area"] = new.loc[new.kind == "area", "name"]

    # drop repeats of the same place (same kind, name and ~100 m)
    new = (new.assign(_k=new.name.str.lower(), _a=new.lat.round(3), _o=new.lon.round(3))
              .drop_duplicates(["kind", "_k", "_a", "_o"])
              .drop(columns=["_k", "_a", "_o"]))

    # the database needs unique names: add the area to names that repeat
    dup = new.name.duplicated(keep=False)
    new.loc[dup, "name"] = new.loc[dup, "name"] + " (" + new.loc[dup, "area"] + ")"
    new["name"] = new["name"] + new.groupby("name").cumcount().map(lambda i: "" if i == 0 else f" #{i + 1}")

    if LM_PATH.exists():
        old = pd.read_csv(LM_PATH)
        shutil.copy(LM_PATH, LM_PATH.with_name("landmarks.backup.csv"))
        # starter rows without an exact position are replaced by the OpenStreetMap row of the same name
        old = old[~(old.lat.isna() & old.name.str.lower().isin(set(new.name.str.lower())))]
        new = new[~new.name.str.lower().isin(old.name.str.lower())]
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    out[COLS].to_csv(LM_PATH, index=False)
    print("\nlandmarks.csv now has:", out.kind.value_counts().to_dict())
    print("Next: python build_db.py")


if __name__ == "__main__":
    main()
