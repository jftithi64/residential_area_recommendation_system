"""Map services: road distance and place search.

Two distance providers, same interface:
  osrm    OpenStreetMap OSRM public server. Free, no key. Driving distance, free-flow time (no traffic).
  google  Google Routes API (computeRouteMatrix). Needs your own API key and a Google Cloud billing
          account; has a monthly free allowance. Traffic-aware time. See README for details.
Place search uses OpenStreetMap Nominatim (free).

The free OSM servers are public demo servers with fair-use limits (about 1 request per second, set a
real User-Agent). Results are cached in the database per provider so each route is requested once.
If the internet or the server is unavailable, distance falls back to a straight-line estimate and is
labelled source='estimate' so it is never mistaken for a real route.
"""
import re
import time

import numpy as np
import requests

import db
from common import haversine_km

OSRM_URL = "https://router.project-osrm.org"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOOGLE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
HEADERS = {"User-Agent": "dhaka-rent-prototype/0.1 (university student project)"}
DHAKA_VIEWBOX = "90.28,23.95,90.55,23.65"  # left, top, right, bottom
CHUNK = 80          # OSRM public server accepts about 100 coordinates per table request
GOOGLE_CHUNK = 100  # origins per Google request (each is one destination, so 100 elements)
TIMEOUT = 20
ROAD_FACTOR = 1.3   # straight-line -> road distance, used only by the offline fallback
CITY_SPEED_KMH = 18  # rough Dhaka traffic speed, used only by the offline fallback
CREDIT = "Map data © OpenStreetMap contributors (ODbL). Road distances: OSRM public demo server."


def geocode_flexible(address, sub, place, limit=6):
    """Try the most specific search first, then simpler ones.

    OpenStreetMap rarely knows building names or flat numbers, so a long address often returns nothing.
    Returns (hits, level, reachable). level is what matched: 'address', 'street', 'block', 'area' or None.
    reachable is False only when the map server itself could not be contacted.
    """
    def clean(t):  # "Modina sorok,Middle bashabo" -> parts; drop house/flat numbers like "1/G"
        return [x.strip() for x in re.split(r"[,;]", t) if x.strip()]
    street_parts = [re.sub(r"\b\d+\s*/?\s*[A-Za-z]?\b", " ", x).strip() for x in clean(address)]
    street_parts = [re.sub(r"\s+", " ", x) for x in street_parts if x]
    tries = [("address", ", ".join(clean(address) + clean(sub) + [place, "Dhaka"])),
             ("street", ", ".join(street_parts + clean(sub) + [place, "Dhaka"]))]
    for part in clean(sub):
        tries.append(("block", f"{part}, {place}, Dhaka"))
    tries.append(("area", f"{place}, Dhaka"))
    seen, reachable = set(), False
    for level, q in tries:
        if q in seen:
            continue
        seen.add(q)
        hits, ok = _geocode(q, limit)
        reachable = reachable or ok
        if hits:
            return hits, level, True
        time.sleep(1.0)  # Nominatim allows about one request per second
    return [], None, reachable


def geocode(query, limit=6):
    """Search OpenStreetMap inside Dhaka. Returns [{'name','lat','lon'}]; [] on failure."""
    return _geocode(query, limit)[0]


def _geocode(query, limit=6):
    """(hits, server_reachable)."""
    try:
        r = requests.get(NOMINATIM_URL, headers=HEADERS, timeout=TIMEOUT, params={
            "q": query, "format": "json", "limit": limit, "viewbox": DHAKA_VIEWBOX,
            "bounded": 1, "countrycodes": "bd"})
        r.raise_for_status()
        return [{"name": x["display_name"], "lat": float(x["lat"]), "lon": float(x["lon"])}
                for x in r.json()], True
    except Exception:
        return [], False


def _osrm_to_destination(dest, points):
    """Road km and minutes from each point to dest, in one table request. points: [(lat, lon)]."""
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in [dest] + list(points))
    r = requests.get(f"{OSRM_URL}/table/v1/driving/{coords}", headers=HEADERS, timeout=TIMEOUT,
                     params={"destinations": 0, "annotations": "distance,duration"})
    r.raise_for_status()
    j = r.json()
    if j.get("code") != "Ok":
        raise RuntimeError(f"OSRM said {j.get('code')}")
    out = []
    for d, t in zip(j["distances"][1:], j["durations"][1:]):  # row 0 is dest -> dest
        d, t = d[0], t[0]
        out.append((np.nan if d is None else d / 1000.0, np.nan if t is None else t / 60.0))
    return out


def _google_to_destination(dest, points, api_key):
    """Road km and minutes (traffic-aware) from each point to dest using Google's Routes API."""
    def wp(lat, lon):
        return {"waypoint": {"location": {"latLng": {"latitude": float(lat), "longitude": float(lon)}}}}
    body = {"origins": [wp(*p) for p in points], "destinations": [wp(*dest)],
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE"}
    r = requests.post(GOOGLE_MATRIX_URL, json=body, timeout=TIMEOUT, headers={
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,distanceMeters,duration,condition"})
    r.raise_for_status()
    out = [(np.nan, np.nan)] * len(points)
    for el in r.json():
        if el.get("condition") != "ROUTE_EXISTS":
            continue
        i = int(el.get("originIndex", 0))
        secs = float(str(el.get("duration", "0s")).rstrip("s") or 0)
        out[i] = (el.get("distanceMeters", 0) / 1000.0, secs / 60.0)  # zero values are omitted in JSON
    return out


def _estimate(dest, point):
    km = float(haversine_km(point, dest)) * ROAD_FACTOR
    return km, km / CITY_SPEED_KMH * 60


def distances(dest, locations, use_network=True, provider="osrm", api_key=None):
    """Distance from each listing location to the destination.

    dest: (lat, lon).  locations: {(place, sub): (lat, lon)}.
    provider: 'osrm' (free) or 'google' (needs api_key; falls back to osrm if no key).
    Returns {(place, sub): (km, minutes, source)} with source 'osrm' / 'google' (real road route)
    or 'estimate' (straight-line guess).
    """
    if provider == "google" and not api_key:
        provider = "osrm"
    result = dict(db.cached_routes(dest[0], dest[1], provider))
    todo = [k for k in locations if k not in result]
    if todo and use_network:
        fresh = []
        step = GOOGLE_CHUNK if provider == "google" else CHUNK
        try:
            for i in range(0, len(todo), step):
                part = todo[i:i + step]
                pts = [locations[k] for k in part]
                got = (_google_to_destination(dest, pts, api_key) if provider == "google"
                       else _osrm_to_destination(dest, pts))
                for key, (km, mn) in zip(part, got):
                    if not np.isnan(km):
                        fresh.append((key[0], key[1], km, mn, provider))
                        result[key] = (km, mn, provider)
                if provider == "osrm" and i + step < len(todo):
                    time.sleep(1)  # be polite to the free server
        except Exception:
            pass  # offline, bad key or rate-limited: the rest fall back below
        if fresh:
            db.save_routes(dest[0], dest[1], fresh)
    for k in todo:
        if k not in result:
            km, mn = _estimate(dest, locations[k])
            result[k] = (km, mn, "estimate")  # not cached, so a later run can fetch the real route
    return {k: result[k] for k in locations}
