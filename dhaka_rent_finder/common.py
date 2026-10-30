"""Shared helpers: paths, cleaning, features, approximate area coordinates."""
import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_RAW = ROOT / "data" / "houserentdhaka.csv"
DATA_CLEAN = ROOT / "data" / "listings_clean.csv"
MODEL_PATH = ROOT / "models" / "rent_model.joblib"
METRICS_PATH = ROOT / "models" / "metrics.json"

CAT_COLS = ["Place", "Sub"]
NUM_COLS = ["Sqft", "LogSqft", "Bed", "Bath"]
FEATURES = CAT_COLS + NUM_COLS

# Sanity limits for removing obvious data-entry errors (see train.py output).
SQFT_RANGE = (250, 6000)
PRICE_RANGE = (3000, 500000)
PPSF_RANGE = (5, 120)  # BDT per sqft per month

# Approximate area centroids (lat, lon) - used ONLY for a rough commute proxy.
# Replace with Google Maps Routes API calls for real travel time (see recommender.py).
AREA_COORDS = {
    "Mirpur": (23.8069, 90.3687), "Mohammadpur": (23.7662, 90.3589),
    "Uttara": (23.8759, 90.3795), "Badda": (23.7806, 90.4258),
    "Bashundhara R-A": (23.8193, 90.4526), "Dakshin Khan": (23.8467, 90.4195),
    "Banasree": (23.7637, 90.4328), "Dhanmondi": (23.7461, 90.3742),
    "Hazaribag": (23.7335, 90.3612), "Adabor": (23.7701, 90.3507),
    "Cantonment": (23.8100, 90.4000), "Malibagh": (23.7490, 90.4130),
    "Khilgaon": (23.7510, 90.4300), "Bashabo": (23.7400, 90.4280),
    "Tejgaon": (23.7590, 90.3930), "Rampura": (23.7600, 90.4200),
    "Maghbazar": (23.7490, 90.4030), "Aftab Nagar": (23.7700, 90.4500),
    "Joar Sahara": (23.8150, 90.4170), "Shyamoli": (23.7740, 90.3650),
    "Agargaon": (23.7780, 90.3800), "Gulshan": (23.7925, 90.4078),
    "Shahjahanpur": (23.7360, 90.4200), "Motijheel": (23.7330, 90.4170),
    "Sutrapur": (23.7110, 90.4150), "Baridhara": (23.8040, 90.4220),
    "Shantinagar": (23.7370, 90.4130), "Lalbagh": (23.7180, 90.3880),
    "Banani": (23.7940, 90.4040), "Eskaton": (23.7450, 90.4020),
    "Kuril": (23.8200, 90.4210), "Kafrul": (23.7960, 90.3830),
    "Nadda": (23.7950, 90.4220), "Kathalbagan": (23.7500, 90.3880),
    "Kalabagan": (23.7510, 90.3750), "Lalmatia": (23.7550, 90.3680),
    "Khilkhet": (23.8290, 90.4200), "Shiddheswari": (23.7440, 90.4100),
    "Hatirpool": (23.7380, 90.3870), "New Market": (23.7330, 90.3850),
    "Nikunja": (23.8300, 90.4150), "Mohakhali": (23.7780, 90.4000),
    "Niketan": (23.7700, 90.4130), "Banani DOHS": (23.7960, 90.4000),
    "Baridhara DOHS": (23.8160, 90.4230), "Mohakhali DOHS": (23.7800, 90.3950),
    "Kakrail": (23.7380, 90.4090), "Shahbagh": (23.7390, 90.3950),
    "Jatra Bari": (23.7100, 90.4350), "Kotwali": (23.7090, 90.4000),
    "Bangshal": (23.7170, 90.4050), "Shegunbagicha": (23.7340, 90.4060),
    "Mugdapara": (23.7330, 90.4300),
}


def parse_price(s):
    """'20 Thousand' -> 20000, '1.2 Lakh' -> 120000 (BDT per month)."""
    m = re.match(r"\s*([\d.,]+)\s*(Thousand|Lakh)", str(s), re.I)
    if not m:
        return np.nan
    v = float(m.group(1).replace(",", ""))
    return v * (1_000 if m.group(2).lower() == "thousand" else 100_000)


def parse_sqft(s):
    m = re.match(r"\s*([\d,.]+)", str(s))
    return float(m.group(1).replace(",", "")) if m else np.nan


def split_location(loc):
    """'Block H, Bashundhara R-A, Dhaka' -> ('Bashundhara R-A', 'Block H')."""
    parts = [p.strip() for p in str(loc).split(",") if p.strip()]
    if parts and parts[-1].lower() == "dhaka":
        parts = parts[:-1]
    if not parts:
        return np.nan, np.nan
    place = parts[-1]
    sub = ", ".join(parts[:-1]) if len(parts) > 1 else "Unknown"
    return place, sub


def add_features(df):
    df = df.copy()
    df["LogSqft"] = np.log1p(df["Sqft"])
    return df


def stable_ids(df, key, space=900_000):
    """Id of a dataset flat from its own content, so survey answers keep pointing at the same flat after a retrain.
    Ids stay below db.BASE_ID (1,000,000), which is reserved for user-added flats; clashes are resolved by probing."""
    used, ids = set(), []
    for row in df[key].astype(str).itertuples(index=False):
        i = int(hashlib.sha1("|".join(row).encode("utf-8")).hexdigest(), 16) % space + 1
        while i in used:
            i = i % space + 1
        used.add(i)
        ids.append(i)
    return ids


def load_clean(verbose=False):
    """Read raw CSV -> parsed, filtered, de-duplicated listings."""
    raw = pd.read_csv(DATA_RAW, index_col=0)
    df = raw.copy()
    df["Price"] = df["Price"].map(parse_price)
    df["Sqft"] = df["Area"].map(parse_sqft)
    loc = df["Location"].map(split_location)
    df["Place"] = loc.map(lambda t: t[0])
    df["Sub"] = loc.map(lambda t: t[1])
    n0 = len(df)
    df = df.dropna(subset=["Price", "Sqft", "Place"])
    n_parse = len(df)
    df = df[df["Sqft"].between(*SQFT_RANGE) & df["Price"].between(*PRICE_RANGE)]
    df = df[(df["Price"] / df["Sqft"]).between(*PPSF_RANGE)]
    n_range = len(df)
    key = ["Location", "Sqft", "Bed", "Bath", "Price"]
    df["dup_count"] = df.groupby(key)["Price"].transform("size")
    df = df.drop_duplicates(subset=key).reset_index(drop=True)
    df["listing_id"] = stable_ids(df, key)
    if verbose:
        print(f"raw rows: {n0} | after parsing: {n_parse} | after range filter: {n_range} "
              f"| after de-duplication: {len(df)}")
    df = add_features(df)
    return df[["listing_id", "Location", "Place", "Sub", "Sqft", "Bed", "Bath",
               "LogSqft", "Price", "dup_count"]]


def haversine_km(a, b):
    """Straight-line distance between two (lat, lon) points in km."""
    lat1, lon1, lat2, lon2 = map(np.radians, [a[0], a[1], b[0], b[1]])
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))
