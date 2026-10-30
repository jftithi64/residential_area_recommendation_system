"""DEMO ONLY: give every dataset row a made-up flat number, house number and road number.

Run:  python make_demo_addresses.py            add placeholder addresses to the original dataset rows
      python make_demo_addresses.py --remove   take them away again

Why: the original dataset has no address, so a row is not a particular house. For a project demo this script adds
a placeholder such as "Flat 4B, House 27, Road 5, Block C, Mirpur, Dhaka" to each row so the app can show exact-
looking flats. THESE ADDRESSES ARE NOT REAL. They are stored with address_source='synthetic_demo' and the app
always shows "[demo address]" next to them. Map positions are NOT invented: distances stay at block level.
The numbers depend only on the listing id, so running the script twice gives the same addresses.
Replace them with real data by adding genuine flats (List a flat page, or import_extra_listings.py).
"""
import sys

import numpy as np

import db

LETTERS = list("ABCDEF")


def demo_address(listing_id, location):
    rng = np.random.default_rng(int(listing_id))
    floor = int(rng.choice(np.arange(1, 11), p=[.18, .17, .16, .14, .11, .09, .07, .04, .03, .01]))
    flat = f"{floor}{LETTERS[int(rng.integers(len(LETTERS)))]}"
    house, road = int(rng.integers(1, 121)), int(rng.integers(1, 31))
    place = location[:-len(", Dhaka")] if location.endswith(", Dhaka") else location
    return f"Flat {flat}, House {house}, Road {road}, {place}, Dhaka"


def apply(con=None):
    """Add placeholder addresses to dataset rows that have none. Returns the number of rows changed."""
    own = con is None
    con = con or db.connect()
    rows = con.execute("SELECT listing_id, location FROM listings WHERE is_extra=0 AND (address IS NULL OR "
                       "address_source='synthetic_demo')").fetchall()
    con.executemany("UPDATE listings SET address=?, address_source='synthetic_demo' WHERE listing_id=?",
                    [(demo_address(i, loc), i) for i, loc in rows])
    con.commit()
    if own:
        con.close()
    return len(rows)


def remove():
    with db.connect() as con:
        cur = con.execute("UPDATE listings SET address=NULL, address_source=NULL WHERE address_source='synthetic_demo'")
        return cur.rowcount


if __name__ == "__main__":
    if "--remove" in sys.argv:
        print("Removed demo addresses from", remove(), "rows.")
    else:
        print("Added placeholder (not real) addresses to", apply(), "rows.")
