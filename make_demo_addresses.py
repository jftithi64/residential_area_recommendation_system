"""DEMO ONLY: give every dataset row a made-up flat number, house number and road number.

Run:  python make_demo_addresses.py --write-csv   edit data/houserentdhaka.csv IN PLACE: put "Flat 4D, House 33, " in
                                                  front of every Location (e.g. "Flat 4D, House 33, Road 3, Baridhara,
                                                  Dhaka"). No new file is made. Rows that already have it are skipped.
      python make_demo_addresses.py --remove-csv  take the prefix off again (exactly restores the original Location)
      python make_demo_addresses.py               (older way) add placeholder addresses to the database rows only
      python make_demo_addresses.py --remove      take those away again
After --write-csv run `python train.py` and `python build_db.py --reset`. The model still sees the Location without
the prefix, so its accuracy and the distances do not change.

Why: the original dataset has no address, so a row is not a particular house. For a project demo this script adds
a placeholder such as "Flat 4B, House 27, Road 5, Block C, Mirpur, Dhaka" to each row so the app can show exact-
looking flats. THESE ADDRESSES ARE NOT REAL. They are stored with address_source='synthetic_demo' and the app
always shows "[demo address]" next to them. Map positions are NOT invented: distances stay at block level.
The numbers depend only on the listing id, so running the script twice gives the same addresses.
Replace them with real data by adding genuine flats (List a flat page, or import_extra_listings.py).
"""
import sys

import numpy as np
import pandas as pd

import db
from common import DATA_RAW, UNIT_RE

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


def write_csv():
    """Prefix every Location in the raw CSV with a random flat and house number (in place). Returns rows changed."""
    raw = pd.read_csv(DATA_RAW, index_col=0)
    todo = ~raw["Location"].astype(str).str.match(UNIT_RE)
    for i in raw.index[todo]:
        rng = np.random.default_rng(int(i))                 # same row -> same flat every time
        floor = int(rng.choice(np.arange(1, 11), p=[.18, .17, .16, .14, .11, .09, .07, .04, .03, .01]))
        flat = f"{floor}{LETTERS[int(rng.integers(len(LETTERS)))]}"
        raw.at[i, "Location"] = f"Flat {flat}, House {int(rng.integers(1, 121))}, {raw.at[i, 'Location']}"
    raw.to_csv(DATA_RAW)
    return int(todo.sum())


def remove_csv():
    raw = pd.read_csv(DATA_RAW, index_col=0)
    had = raw["Location"].astype(str).str.match(UNIT_RE)
    raw.loc[had, "Location"] = raw.loc[had, "Location"].astype(str).str.replace(UNIT_RE, "", regex=True)
    raw.to_csv(DATA_RAW)
    return int(had.sum())


def remove():
    with db.connect() as con:
        cur = con.execute("UPDATE listings SET address=NULL, address_source=NULL WHERE address_source='synthetic_demo'")
        return cur.rowcount


if __name__ == "__main__":
    if "--write-csv" in sys.argv:
        print("Added placeholder (not real) flat and house numbers to", write_csv(), "Location values in", DATA_RAW.name)
        print("Next: python train.py   then   python build_db.py --reset")
    elif "--remove-csv" in sys.argv:
        print("Removed the flat and house numbers from", remove_csv(), "Location values.")
    elif "--remove" in sys.argv:
        print("Removed demo addresses from", remove(), "rows.")
    else:
        print("Added placeholder (not real) addresses to", apply(), "rows.")
