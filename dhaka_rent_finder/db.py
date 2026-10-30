"""SQLite database layer (data/rent.db).

Tables
  listings         rent listings: the original dataset plus flats added by users (is_extra=1)
  landmarks        schools / colleges / universities the user can pick as destination
  location_coords  latitude/longitude of each (place, sub-area); sub='' means the area centre
  route_cache      road distance/time from a destination to each location, per map provider
  pairwise         A/B survey answers used to train the learned ranker
  model_log        accuracy of the rent model on user-added flats, one row per check
  imports          fingerprints of imported form rows, so a row is never imported twice

User-added flats have a status: pending -> approved (shown in results) or rejected;
approved -> rented / expired / removed. Only 'approved' flats of kind 'available' are recommended.
"""
import json
import sqlite3
from datetime import date

import pandas as pd

from common import AREA_COORDS, ROOT

DB_PATH = ROOT / "data" / "rent.db"
BASE_ID = 1_000_000   # user-added flats get ids from here, so they never clash with the dataset

ROUTE_CACHE_DDL = """
CREATE TABLE IF NOT EXISTS route_cache(
  dest_lat REAL, dest_lon REAL, place TEXT, sub TEXT, distance_km REAL, duration_min REAL,
  source TEXT, PRIMARY KEY(dest_lat, dest_lon, place, sub, source));
"""

BASE_COLS = ("listing_id INTEGER PRIMARY KEY, location TEXT, place TEXT, sub TEXT, sqft REAL, bed INTEGER, "
             "bath INTEGER, price REAL, fair_rent REAL, dup_count INTEGER")
EXTRA_COLS = [
    ("tenant_rule", "TEXT"), ("floor", "INTEGER"), ("lift", "INTEGER"), ("gas", "INTEGER"),
    ("available_from", "TEXT"), ("source_url", "TEXT"), ("is_extra", "INTEGER DEFAULT 0"),
    ("status", "TEXT DEFAULT 'approved'"), ("entry_kind", "TEXT DEFAULT 'available'"),
    ("listed_at", "TEXT"), ("updated_at", "TEXT"), ("address", "TEXT"), ("lat", "REAL"), ("lon", "REAL"),
    ("parking", "INTEGER"), ("generator", "INTEGER"), ("furnished", "INTEGER"), ("advance_months", "REAL"),
    ("rent_type", "TEXT DEFAULT 'asking'"), ("contact", "TEXT"), ("contact_public", "INTEGER DEFAULT 0"),
    ("edit_code_hash", "TEXT"), ("flags", "TEXT"), ("address_source", "TEXT")]
LISTING_FIELDS = ["listing_id", "location", "place", "sub", "sqft", "bed", "bath", "price", "fair_rent",
                  "dup_count"] + [n for n, _ in EXTRA_COLS]
PRIVATE_COLS = ["edit_code_hash", "contact"]
STATUSES = ["pending", "approved", "rejected", "rented", "expired", "removed"]

LISTINGS_DDL = "CREATE TABLE IF NOT EXISTS listings(" + BASE_COLS + "".join(f", {n} {t}" for n, t in EXTRA_COLS) + ");"

SCHEMA = LISTINGS_DDL + """
CREATE TABLE IF NOT EXISTS landmarks(
  landmark_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, kind TEXT, area TEXT,
  lat REAL, lon REAL, coord_source TEXT);
CREATE TABLE IF NOT EXISTS location_coords(
  place TEXT, sub TEXT, lat REAL, lon REAL, source TEXT, PRIMARY KEY(place, sub));
CREATE TABLE IF NOT EXISTS pairwise(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT CURRENT_TIMESTAMP, person_id TEXT,
  destination TEXT, listing_a INTEGER, listing_b INTEGER, choice INTEGER,
  feat_a TEXT, feat_b TEXT, context TEXT, synthetic INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS model_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT CURRENT_TIMESTAMP, n INTEGER, mae REAL,
  mape REAL, within20 REAL, note TEXT);
CREATE TABLE IF NOT EXISTS imports(row_hash TEXT PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP);
""" + ROUTE_CACHE_DDL


def _migrate(con):
    """Upgrade a database made by an older version of this project."""
    have = {r[1] for r in con.execute("PRAGMA table_info(listings)")}
    for name, typ in EXTRA_COLS:
        if name not in have:
            con.execute(f"ALTER TABLE listings ADD COLUMN {name} {typ}")
    pk = {r[1] for r in con.execute("PRAGMA table_info(route_cache)") if r[5]}
    if "source" not in pk:  # old cache had no provider in its key; it is only a cache, so rebuild it
        con.execute("DROP TABLE route_cache")
        con.executescript(ROUTE_CACHE_DDL)
    con.commit()


INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_listings_status_place ON listings(status, place);
CREATE INDEX IF NOT EXISTS idx_listings_extra ON listings(is_extra, status);
CREATE INDEX IF NOT EXISTS idx_pairwise_person ON pairwise(person_id);
"""


class _Conn(sqlite3.Connection):
    """`with connect() as con:` commits (or rolls back) AND closes, so no connection is left open."""

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


_READY = False   # schema is created / upgraded once per process, not on every call


def connect():
    global _READY
    DB_PATH.parent.mkdir(exist_ok=True)
    if not DB_PATH.exists():
        _READY = False
    con = sqlite3.connect(DB_PATH, factory=_Conn, timeout=30)
    if not _READY:
        con.execute("PRAGMA journal_mode=WAL")   # readers do not block the writer
        con.executescript(SCHEMA)
        _migrate(con)
        con.executescript(INDEX_DDL)
        _READY = True
    return con


def exists():
    if not DB_PATH.exists():
        return False
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM listings").fetchone()[0] > 0


# ------------------------------------------------------------------ listings
def load_listings(include_private=False):
    """All listings, every status. Columns lat/lon (a flat's exact position) are named exact_lat/exact_lon."""
    with connect() as con:
        df = pd.read_sql_query("SELECT * FROM listings", con)
    df = df.rename(columns={"location": "Location", "place": "Place", "sub": "Sub", "sqft": "Sqft", "bed": "Bed",
                            "bath": "Bath", "price": "Price", "lat": "exact_lat", "lon": "exact_lon"})
    if not include_private:
        df = df.drop(columns=PRIVATE_COLS, errors="ignore")
    return df


def get_listing(listing_id):
    with connect() as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM listings WHERE listing_id=?", (int(listing_id),)).fetchone()
    return dict(row) if row else None


def add_listing(rec):
    """Insert a user-added flat. rec uses the database column names. Returns the new listing_id."""
    today = date.today().isoformat()
    rec = {"dup_count": 1, "is_extra": 1, "status": "pending", "entry_kind": "available", "rent_type": "asking",
           "listed_at": today, "updated_at": today, **rec}
    bad = set(rec) - set(LISTING_FIELDS)
    if bad:
        raise ValueError(f"unknown listing fields: {sorted(bad)}")
    if rec.get("address") and not rec.get("address_source"):
        rec["address_source"] = "user"          # typed in by the owner, as opposed to a made-up demo address
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")   # take the write lock first so two people cannot get the same id
        top = con.execute("SELECT MAX(listing_id) FROM listings").fetchone()[0] or 0
        rec["listing_id"] = max(BASE_ID, top + 1)
        cols = list(rec)
        con.execute(f"INSERT INTO listings({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [rec[c] for c in cols])
    return rec["listing_id"]


def update_listing(listing_id, touch=True, **fields):
    """Change fields of a flat. touch=True refreshes updated_at (it also restarts the expiry clock)."""
    bad = set(fields) - set(LISTING_FIELDS) - {"listing_id"}
    if bad or not fields:
        raise ValueError(f"bad fields: {sorted(bad)}")
    if touch:
        fields["updated_at"] = date.today().isoformat()
    with connect() as con:
        con.execute(f"UPDATE listings SET {', '.join(k + '=?' for k in fields)} WHERE listing_id=?",
                    [*fields.values(), int(listing_id)])


def set_status(listing_id, status, touch=True):
    if status not in STATUSES:
        raise ValueError(status)
    update_listing(listing_id, touch=touch, status=status)


def find_duplicate(place, sub, sqft, bed, bath, price):
    """id of a similar user-added flat that is still pending/approved (same block, size within 3%, rent within 5%)."""
    with connect() as con:
        row = con.execute(
            "SELECT listing_id FROM listings WHERE is_extra=1 AND status IN ('pending','approved') AND place=? "
            "AND sub=? AND bed=? AND bath=? AND ABS(sqft-?) <= 0.03*? AND ABS(price-?) <= 0.05*? LIMIT 1",
            (place, sub, int(bed), int(bath), sqft, sqft, price, price)).fetchone()
    return row[0] if row else None


def public_contacts(listing_ids):
    """{listing_id: contact} only for flats whose owner chose to show contact details."""
    ids = [int(i) for i in listing_ids]
    if not ids:
        return {}
    with connect() as con:
        rows = con.execute(f"SELECT listing_id, contact FROM listings WHERE contact_public=1 AND status='approved' "
                           f"AND contact IS NOT NULL AND listing_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    return dict(rows)


# ------------------------------------------------------------------ landmarks and coordinates
def load_landmarks(kind=None):
    q, args = "SELECT * FROM landmarks", ()
    if kind:
        q, args = q + " WHERE kind=?", (kind,)
    with connect() as con:
        return pd.read_sql_query(q + " ORDER BY name", con, params=args)


def location_coords():
    """{(place, sub): (lat, lon, source)}; area centres are stored with sub=''."""
    with connect() as con:
        rows = con.execute("SELECT place, sub, lat, lon, source FROM location_coords").fetchall()
    out = {(p, s): (la, lo, src) for p, s, la, lo, src in rows}
    for place, (la, lo) in AREA_COORDS.items():  # safety net if the table is empty
        out.setdefault((place, ""), (la, lo, "manual_centroid"))
    return out


def coord_key(coords, place, sub):
    """Most precise known point for a listing: block/sub-area first, then the area centre."""
    if (place, sub) in coords:
        return (place, sub)
    if (place, "") in coords:
        return (place, "")
    return None


# ------------------------------------------------------------------ route cache
def cached_routes(dest_lat, dest_lon, source):
    with connect() as con:
        rows = con.execute("SELECT place, sub, distance_km, duration_min FROM route_cache "
                           "WHERE dest_lat=? AND dest_lon=? AND source=?",
                           (round(dest_lat, 4), round(dest_lon, 4), source)).fetchall()
    return {(p, s): (d, t, source) for p, s, d, t in rows}


def save_routes(dest_lat, dest_lon, rows):
    """rows: iterable of (place, sub, km, minutes, source)."""
    with connect() as con:
        con.executemany("INSERT OR REPLACE INTO route_cache VALUES (?,?,?,?,?,?,?)",
                        [(round(dest_lat, 4), round(dest_lon, 4), p, s, d, t, src) for p, s, d, t, src in rows])


# ------------------------------------------------------------------ survey and model log
def add_pair(person_id, destination, listing_a, listing_b, choice, feat_a, feat_b, context, synthetic=0):
    """choice = 1 if flat A was preferred, 0 if flat B was preferred."""
    with connect() as con:
        con.execute("INSERT INTO pairwise(person_id, destination, listing_a, listing_b, choice, feat_a, feat_b, "
                    "context, synthetic) VALUES (?,?,?,?,?,?,?,?,?)",
                    (person_id, destination, int(listing_a), int(listing_b), int(choice), json.dumps(feat_a),
                     json.dumps(feat_b), json.dumps(context), int(synthetic)))


def pairs_df():
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM pairwise", con)


def add_model_log(n, mae, mape, within20, note=""):
    with connect() as con:
        con.execute("INSERT INTO model_log(n, mae, mape, within20, note) VALUES (?,?,?,?,?)",
                    (int(n), float(mae), float(mape), float(within20), note))


def model_log_df():
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM model_log ORDER BY id", con)
