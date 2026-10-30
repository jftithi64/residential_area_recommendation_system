"""Collect REAL flats (with road and house) for areas that have no rent data yet.

Nobody can generate real rents for you: people have to read real adverts, ask owners / renters, or visit.
This tool checks what they typed, refuses bad or private rows, removes repeats, and stores the good rows in
data/collected_real.csv. The next `python train.py` uses them to teach the rent model those areas.

  python collect_data.py template                 write data/collected_template.csv (headers only)
  python collect_data.py check  my_rows.csv       check a file, change nothing
  python collect_data.py add    my_rows.csv       check, then store the good rows (bad rows are listed, not stored)
  python collect_data.py add    my_rows.csv --train   ... then run train.py and build_db.py
  python collect_data.py status                   rows per area against the target (20), writes data/area_progress.csv

Columns of a row
  area         an area from the site's list (for example Azimpur)
  road         road / block / sector as written in the advert, e.g. "Road 3" or "Block C"        (required)
  house_no     house or holding number, e.g. "12" or "12/A"                                         (required)
  flat         flat / unit, e.g. "4B" (optional; the leading digits are used as the floor)
  floor        floor number (optional)
  sqft, bed, bath, rent_bdt     rent is per month in taka; "18 Thousand" and "18,000" both work
  source_type  advert | survey | broker | visit
  source_url   link to the advert (required when source_type is advert)
  date_seen    YYYY-MM-DD, the day you saw the advert or asked the person
  notes        optional, free text (no phone numbers or names)

Rules that protect people: rows containing a phone number or email address are refused, and no owner or
broker names are stored. Only the road, house and flat details (what an advert shows) are kept.
"""
import re
import subprocess
import sys
from datetime import date, datetime

import pandas as pd

import common
from common import AREA_COORDS, PPSF_RANGE, PRICE_RANGE, ROOT, SQFT_RANGE

TARGET = 20
COLUMNS = ["area", "road", "house_no", "flat", "floor", "sqft", "bed", "bath", "rent_bdt",
           "source_type", "source_url", "date_seen", "notes"]
SOURCE_TYPES = ("advert", "survey", "broker", "visit")
PHONE_RE = re.compile(r"(\+?880|\b0)\s*1[3-9][\d\s\-]{8,}")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
MAX_AGE_DAYS = 365
TEMPLATE_PATH = ROOT / "data" / "collected_template.csv"
PROGRESS_PATH = ROOT / "data" / "area_progress.csv"


def canonical_area(name):
    """'  azimpur ' -> 'Azimpur' (the spelling the site uses), or None if the area is not in the site's list."""
    key = " ".join(str(name or "").split()).lower()
    for a in AREA_COORDS:
        if a.lower() == key:
            return a
    return None


def _num(text):
    s = str(text or "").strip()
    if not s:
        return None
    price = common.parse_price(s)                 # "18 Thousand", "1.2 Lakh"
    if price == price:                            # not NaN
        return float(price)
    s = re.sub(r"(?i)\s*(sqft|sq\.?\s*ft|tk|taka|bdt|৳)\s*", "", s).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _key(r):
    return tuple(str(r[k]).strip().lower() for k in ("area", "road", "house_no", "flat", "sqft", "bed", "bath", "rent_bdt"))


def validate_row(raw, today=None):
    """Returns (clean_row_dict or None, [error messages])."""
    today = today or date.today()
    errs = []
    r = {c: str(raw.get(c, "") if raw.get(c, "") == raw.get(c, "") else "").strip() for c in COLUMNS}
    for field, value in r.items():
        if PHONE_RE.search(value) or EMAIL_RE.search(value):
            errs.append(f"{field}: contains a phone number or email address (not allowed)")
    area = canonical_area(r["area"])
    if not area:
        errs.append(f"area '{r['area']}' is not in the site's area list (see EXTRA_AREA_COORDS in common.py)")
    road, house = " ".join(r["road"].split()), " ".join(r["house_no"].split())
    if not road:
        errs.append("road is required (the road, block or sector from the advert)")
    if not house:
        errs.append("house_no is required")
    sqft, rent = _num(r["sqft"]), _num(r["rent_bdt"])
    bed, bath = _num(r["bed"]), _num(r["bath"])
    if sqft is None or not SQFT_RANGE[0] <= sqft <= SQFT_RANGE[1]:
        errs.append(f"sqft must be a number between {SQFT_RANGE[0]} and {SQFT_RANGE[1]}")
    if rent is None or not PRICE_RANGE[0] <= rent <= PRICE_RANGE[1]:
        errs.append(f"rent_bdt must be a monthly rent between {PRICE_RANGE[0]:,} and {PRICE_RANGE[1]:,} taka")
    for name, v in (("bed", bed), ("bath", bath)):
        if v is None or v != int(v) or not 1 <= v <= 10:
            errs.append(f"{name} must be a whole number from 1 to 10")
    if sqft and rent and SQFT_RANGE[0] <= sqft <= SQFT_RANGE[1] and PRICE_RANGE[0] <= rent <= PRICE_RANGE[1]:
        ppsf = rent / sqft
        if not PPSF_RANGE[0] <= ppsf <= PPSF_RANGE[1]:
            errs.append(f"rent per sqft is {ppsf:.0f} taka, outside {PPSF_RANGE[0]}-{PPSF_RANGE[1]} "
                        "(a typing mistake, or sqft and rent mixed up?)")
    st = r["source_type"].lower()
    if st not in SOURCE_TYPES:
        errs.append(f"source_type must be one of: {', '.join(SOURCE_TYPES)}")
    if st == "advert" and not r["source_url"].lower().startswith(("http://", "https://")):
        errs.append("source_url (a link to the advert) is required when source_type is advert")
    try:
        seen = datetime.strptime(r["date_seen"], "%Y-%m-%d").date()
        if seen > today:
            errs.append("date_seen is in the future")
        elif (today - seen).days > MAX_AGE_DAYS:
            errs.append(f"date_seen is more than {MAX_AGE_DAYS} days old; rents change, collect a fresher row")
    except ValueError:
        errs.append("date_seen must look like 2026-10-27")
    floor = _num(r["floor"])
    if r["floor"] and (floor is None or floor != int(floor) or not 0 <= floor <= 60):
        errs.append("floor must be a whole number")
    if errs:
        return None, errs
    return {"area": area, "road": road, "house_no": house, "flat": r["flat"], "floor": "" if floor is None else int(floor),
            "sqft": int(round(sqft)), "bed": int(bed), "bath": int(bath), "rent_bdt": int(round(rent)),
            "source_type": st, "source_url": r["source_url"], "date_seen": r["date_seen"],
            "notes": r["notes"]}, []


def read_existing():
    if common.COLLECTED_PATH.exists():
        return pd.read_csv(common.COLLECTED_PATH, dtype=str).fillna("")
    return pd.DataFrame(columns=COLUMNS)


def check_file(path, today=None):
    """Returns (good_rows, problems, repeats). problems: [(csv_line_number, [messages])]. repeats: [csv_line_number]."""
    table = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in COLUMNS if c not in table.columns and c not in ("flat", "floor", "notes", "source_url")]
    if missing:
        raise ValueError(f"The file is missing these columns: {', '.join(missing)}. Run `python collect_data.py template`.")
    existing = read_existing()
    seen = {_key(r) for r in existing.to_dict("records")} if len(existing) else set()
    good, problems, repeats = [], [], []
    for i, raw in enumerate(table.to_dict("records")):
        line = i + 2                                    # line 1 is the header
        row, errs = validate_row(raw, today)
        if errs:
            problems.append((line, errs))
            continue
        k = _key(row)
        if k in seen:
            repeats.append(line)
            continue
        seen.add(k)
        good.append(row)
    return good, problems, repeats


def add_rows(good):
    old = read_existing()
    new = pd.concat([old, pd.DataFrame(good, columns=COLUMNS).astype(str)], ignore_index=True)
    common.COLLECTED_PATH.parent.mkdir(exist_ok=True)
    new.to_csv(common.COLLECTED_PATH, index=False)
    return len(new)


def status():
    """DataFrame: one row per area that is below the target, most missing first. Counts the rows the model will use."""
    df = common.load_clean()
    counts = df.Place.value_counts()
    collected = read_existing()
    raw = collected.area.value_counts() if len(collected) else pd.Series(dtype=int)
    rows = []
    for a in sorted(AREA_COORDS):
        n = int(counts.get(a, 0))
        rows.append({"area": a, "usable_rows": n, "collected_rows": int(raw.get(a, 0)), "target": TARGET,
                     "still_needed": max(0, TARGET - n),
                     "status": "ok" if n >= TARGET else ("started" if n else "no data")})
    out = pd.DataFrame(rows)
    return out.sort_values(["still_needed", "area"], ascending=[False, True]).reset_index(drop=True)


def _report(good, problems, repeats):
    print(f"{len(good)} row(s) are good, {len(problems)} have problems, {len(repeats)} already stored.")
    for line, errs in problems:
        print(f"  line {line}:")
        for e in errs:
            print(f"    - {e}")
    if repeats:
        print(f"  repeats (same flat, size and rent already stored): lines {', '.join(map(str, repeats))}")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "template":
        TEMPLATE_PATH.parent.mkdir(exist_ok=True)
        pd.DataFrame(columns=COLUMNS).to_csv(TEMPLATE_PATH, index=False)
        print(f"Wrote {TEMPLATE_PATH}. Fill one row per real flat, then run: python collect_data.py check <file>")
    elif cmd in ("check", "add"):
        if len(args) < 2:
            sys.exit("Give the CSV file: python collect_data.py " + cmd + " my_rows.csv")
        try:
            good, problems, repeats = check_file(args[1])
        except (ValueError, OSError) as e:
            sys.exit(str(e))
        _report(good, problems, repeats)
        if cmd == "add":
            if good:
                total = add_rows(good)
                print(f"Stored {len(good)} row(s). data/collected_real.csv now has {total}.")
            else:
                print("Nothing to store.")
            if "--train" in argv and good:
                for script in ("train.py", "build_db.py"):
                    print(f"Running {script} ...")
                    subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=ROOT)
            elif good:
                print("Next: python train.py, then python build_db.py (or run add again with --train).")
    elif cmd == "status":
        table = status()
        PROGRESS_PATH.parent.mkdir(exist_ok=True)
        table.to_csv(PROGRESS_PATH, index=False)
        short = table[table.still_needed > 0]
        print(f"{len(table) - len(short)} of {len(table)} areas have at least {TARGET} usable rows. "
              f"{len(short)} still need data (saved to {PROGRESS_PATH}):")
        print(short.to_string(index=False))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
