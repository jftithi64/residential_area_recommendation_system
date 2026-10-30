"""Photos of listed flats. Files live in data/photos/, one row per photo in table listing_photos.

Every upload is opened with Pillow, rotated the way the camera meant, shrunk to 1280 px, and re-saved as a plain
JPEG. That also removes hidden camera data such as the GPS position of the photo, and rejects files that are not
real pictures.
"""
import io
import secrets
from datetime import datetime

from PIL import Image, ImageOps

import db
from common import ROOT

PHOTO_DIR = ROOT / "data" / "photos"
MAX_PHOTOS = 5
MAX_UPLOAD_MB = 8
MAX_SIDE = 1280
Image.MAX_IMAGE_PIXELS = 40_000_000   # refuse absurdly large images

DDL = ("CREATE TABLE IF NOT EXISTS listing_photos(photo_id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id INTEGER, "
       "filename TEXT, created_at TEXT)")


def _connect():
    con = db.connect()
    con.execute(DDL)
    return con


def count(listing_id):
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM listing_photos WHERE listing_id=?", (int(listing_id),)).fetchone()[0]


def add_photo(listing_id, data):
    """Clean and store one uploaded picture (bytes). Returns the photo_id. Raises ValueError with a plain message."""
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"Each photo must be smaller than {MAX_UPLOAD_MB} MB.")
    if count(listing_id) >= MAX_PHOTOS:
        raise ValueError(f"A flat can have at most {MAX_PHOTOS} photos. Delete one first.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("That file is not a picture we can read. Use JPG, PNG or WebP.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(listing_id)}_{secrets.token_hex(6)}.jpg"
    img.save(PHOTO_DIR / name, "JPEG", quality=80, optimize=True)   # no exif argument: hidden data is dropped
    with _connect() as con:
        cur = con.execute("INSERT INTO listing_photos(listing_id, filename, created_at) VALUES (?,?,?)",
                          (int(listing_id), name, datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid


def photos_for(listing_id):
    """[(photo_id, Path)] for one flat, oldest first. Rows whose file is missing are skipped."""
    with _connect() as con:
        rows = con.execute("SELECT photo_id, filename FROM listing_photos WHERE listing_id=? ORDER BY photo_id",
                           (int(listing_id),)).fetchall()
    return [(i, PHOTO_DIR / f) for i, f in rows if (PHOTO_DIR / f).exists()]


def first_photos(listing_ids):
    """{listing_id: Path} with the first photo of each flat that has one."""
    ids = [int(i) for i in listing_ids]
    if not ids:
        return {}
    with _connect() as con:
        rows = con.execute(f"SELECT listing_id, filename FROM listing_photos WHERE listing_id IN "
                           f"({','.join('?' * len(ids))}) ORDER BY photo_id DESC", ids).fetchall()
    out = {}
    for lid, f in rows:           # DESC + overwrite leaves the oldest photo as the cover
        if (PHOTO_DIR / f).exists():
            out[lid] = PHOTO_DIR / f
    return out


def delete_photo(photo_id, listing_id):
    """Delete one photo, only if it belongs to this listing."""
    with _connect() as con:
        row = con.execute("SELECT filename FROM listing_photos WHERE photo_id=? AND listing_id=?",
                          (int(photo_id), int(listing_id))).fetchone()
        if not row:
            return False
        con.execute("DELETE FROM listing_photos WHERE photo_id=?", (int(photo_id),))
    try:
        (PHOTO_DIR / row[0]).unlink()
    except FileNotFoundError:
        pass
    return True
