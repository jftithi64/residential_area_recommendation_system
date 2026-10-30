"""Suggestions for the 'List a flat' page: which areas and landmarks are close to this flat?

Straight-line distances are used only to PICK and SORT the suggestions (fast, no internet).
Once the owner/renter chooses one, call road_distance() to get the real road km and minutes.

Example for views/list_flat.py:
    import nearby
    opts = nearby.suggest(place, sub, exact=None, k_areas=8, k_landmarks=10)
    st.caption("Nearby areas (straight line): " + ", ".join(f"{a['area']} {a['km']} km" for a in opts["areas"]))
    pick = st.multiselect("Places people may travel to from here",
                          [f"{x['name']} ({x['kind']}, ~{x['km']} km)" for x in opts["landmarks"]])
"""
import pandas as pd

import db
import maps
from common import haversine_km


def _origin(place, sub, exact=None):
    """Most precise known point: exact (lat, lon) > block > area centre. None if unknown."""
    if exact and None not in exact and not pd.isna(exact[0]):
        return (float(exact[0]), float(exact[1]))
    coords = db.location_coords()
    k = db.coord_key(coords, place, sub or "")
    return (coords[k][0], coords[k][1]) if k else None


def nearby_areas(place, k=8, max_km=8.0):
    """The k closest other areas, nearest first: [{'area', 'km', 'lat', 'lon'}]."""
    centres = {p: (la, lo) for (p, s), (la, lo, _) in db.location_coords().items() if s == ""}
    if place not in centres:
        return []
    here = centres[place]
    rows = sorted((float(haversine_km(here, c)), p) for p, c in centres.items() if p != place)
    return [{"area": p, "km": round(d, 1), "lat": centres[p][0], "lon": centres[p][1]}
            for d, p in rows if d <= max_km][:k]


def nearby_landmarks(place, sub=None, exact=None, kinds=None, k=10, max_km=6.0):
    """Closest schools / colleges / universities / offices / areas: [{'name', 'kind', 'km', 'lat', 'lon'}]."""
    origin = _origin(place, sub, exact)
    if origin is None:
        return []
    lm = db.load_landmarks().dropna(subset=["lat", "lon"])
    if kinds:
        lm = lm[lm.kind.isin(kinds)]
    if lm.empty:
        return []
    lm = lm.assign(km=[float(haversine_km(origin, (a, b))) for a, b in zip(lm.lat, lm.lon)])
    lm = lm[lm.km <= max_km].sort_values("km").head(k)
    return [{"name": r.name, "kind": r.kind, "km": round(r.km, 1), "lat": r.lat, "lon": r.lon}
            for r in lm.itertuples()]


def suggest(place, sub=None, exact=None, k_areas=8, k_landmarks=10, kinds=None):
    return {"areas": nearby_areas(place, k_areas),
            "landmarks": nearby_landmarks(place, sub, exact, kinds, k_landmarks)}


def road_distance(place, sub, target_lat, target_lon, exact=None, provider="osrm", api_key=None, use_network=True):
    """Real road distance from the flat to a chosen place: (km, minutes, source); source 'estimate' if offline."""
    origin = _origin(place, sub, exact)
    if origin is None:
        return None
    key = (place, sub or "")
    res = maps.distances((target_lat, target_lon), {key: origin}, use_network=use_network,
                         provider=provider, api_key=api_key)
    return res[key]
