"""Listing-level recommender.

Pipeline (matches the project diagram):
  user input -> map distance -> ML fair rent -> weighted score (baseline)
  -> learned pairwise ranker (trained from A/B survey answers, optional) -> ranked specific listings

Two steps, so the app can reuse the filtered pool for ranking AND for the A/B survey:
  prepare(...)  filter listings, measure distance, compute travel cost and the numeric features
  rank(...)     score and sort the prepared pool
"""
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

import db
import listing_logic
import maps
from common import FEATURES, MODEL_PATH, ROOT, add_features

RANKER_PATH = ROOT / "models" / "ranker.joblib"

# What the learned ranker sees. Every value describes one flat for one person's situation.
FEATURE_NAMES = ["price_ratio", "deal_gap", "size_gap", "bed_extra", "bath", "km", "travel_ratio"]
DEFAULT_WEIGHTS = {"w_value": 5, "w_space": 3, "w_commute": 5, "w_savings": 2}

# Assumptions (editable in the app). They are NOT measured from data.
TRIPS_PER_MONTH = 22      # round trips to school/office per month
FARE_PER_KM = 5.0         # BDT per km, blended rickshaw / CNG / bus guess
WALK_KM = 1.5             # closer than this counts as walking (no fare)
ADVANCE_MONTHS = 2        # typical advance deposit, in months of rent
TENANT_TYPES = ["Any / not sure", "Family", "Bachelor (male)", "Bachelor (female)"]
TENANT_CODES = {"Family": "family", "Bachelor (male)": "bachelor_male", "Bachelor (female)": "bachelor_female"}


@lru_cache(maxsize=1)
def load_model():
    return joblib.load(MODEL_PATH)


def load_ranker():
    """The learned ranker if train_ranker.py has produced one, else None."""
    return joblib.load(RANKER_PATH) if RANKER_PATH.exists() else None


def places():
    return sorted(db.load_listings()["Place"].unique())


def default_target_sqft(bed):
    """Typical size of a flat with this many bedrooms (median of the data), rounded to 50 sqft."""
    df = db.load_listings()
    sub = df[df.Bed == bed]
    med = sub.Sqft.median() if len(sub) >= 20 else df.Sqft.median()
    return int(round(med / 50) * 50)


def predict_fair_rent(place, sub, sqft, bed, bath):
    """ML estimate of a fair monthly rent for any flat description."""
    row = add_features(pd.DataFrame([{"Place": place, "Sub": sub or "Unknown",
                                      "Sqft": sqft, "Bed": bed, "Bath": bath}]))
    return float(np.expm1(load_model().predict(row[FEATURES])[0]))


def baseline_from_features(f, cap=10.0, use_commute=True, weights=None):
    """Weighted baseline score 0-100 from the feature table (DataFrame). cap and use_commute may be arrays."""
    w = weights or DEFAULT_WEIGHTS
    s_value = (f["deal_gap"].clip(-0.3, 0.3) + 0.3) / 0.6   # gaps beyond +/-30% are more likely missing info
    s_space = (1 - f["size_gap"]).clip(0, 1)                 # closeness to the size the person wants
    s_savings = (1 - f["price_ratio"]).clip(0, 1)
    s_commute = (1 - f["km"] / cap).clip(0, 1)
    wc = w["w_commute"] * np.asarray(use_commute, dtype=float)
    total = w["w_value"] + w["w_space"] + wc + w["w_savings"]
    total = np.where(total == 0, 1, total)
    return (w["w_value"] * s_value + w["w_space"] * s_space + wc * s_commute + w["w_savings"] * s_savings) / total * 100


def prepare(budget_max, budget_min=0, min_bed=1, max_bed=6, min_bath=1, min_sqft=0, target_sqft=None,
            preferred_places=None, destination=None, max_km=None, tenant=None, strict_tenant=False,
            trips_per_month=TRIPS_PER_MONTH, fare_per_km=FARE_PER_KM, walk_km=WALK_KM,
            provider="osrm", api_key=None, use_network=True):
    """Filter the listings and attach distance, travel cost and the ranker features.

    destination = {'name','lat','lon'} or None.  tenant = 'family' / 'bachelor_male' / ... or None.
    """
    df = db.load_listings()
    live = df.status.fillna("approved").eq("approved") & df.entry_kind.fillna("available").eq("available")
    df = df[live & (df.Price <= budget_max) & (df.Price >= budget_min) & (df.Bed >= min_bed) & (df.Bed <= max_bed)
            & (df.Bath >= min_bath) & (df.Sqft >= min_sqft)].copy()
    if preferred_places:
        df = df[df.Place.isin(preferred_places)]
    if tenant:  # most listings have no tenant rule in the data; unknown ones stay unless strict
        known_ok = df.tenant_rule.isin(["any", tenant])
        df = df[known_ok] if strict_tenant else df[known_ok | df.tenant_rule.isna()]
    if df.empty:
        return df

    # ---- map: coordinates of each listing, then road distance to the destination
    coords = db.location_coords()
    keys, points = [], {}
    for p, s, la, lo in zip(df.Place, df.Sub, df.exact_lat, df.exact_lon):
        if pd.notna(la) and pd.notna(lo):     # a flat with its own exact map position (user-added)
            k = ("@exact", f"{la:.5f},{lo:.5f}")
            points[k] = (float(la), float(lo))
        else:                                 # otherwise the block, or the area centre
            k = db.coord_key(coords, p, s)
            if k:
                points[k] = (coords[k][0], coords[k][1])
        keys.append(k)
    df["km"], df["minutes"], df["dist_source"] = np.nan, np.nan, None
    df["lat"] = [points[k][0] if k else np.nan for k in keys]
    df["lon"] = [points[k][1] if k else np.nan for k in keys]
    if destination:
        dist = maps.distances((destination["lat"], destination["lon"]), points, use_network=use_network,
                              provider=provider, api_key=api_key)
        df["km"] = [dist[k][0] if k else np.nan for k in keys]
        df["minutes"] = [dist[k][1] if k else np.nan for k in keys]
        df["dist_source"] = [dist[k][2] if k else None for k in keys]
        if max_km:  # unknown distances are dropped when a limit is set
            df = df[df.km <= max_km]
    if df.empty:
        return df

    # ---- costs. travel cost is an assumption-based estimate (round trips x km x fare), walking is free
    # A flat whose distance is unknown must NOT look like the closest one: give it the worst known distance.
    km = df.km.fillna(df.km.max() if df.km.notna().any() else 0)
    df["travel_cost"] = np.where(km <= walk_km, 0.0, km * 2 * trips_per_month * fare_per_km).round(-1)
    df["total_monthly"] = df.Price + df.travel_cost
    df["advance"] = np.nan  # filled by the app from the person's "advance months" setting

    # ---- features
    target = target_sqft or default_target_sqft(min_bed)
    raw_gap = (df.fair_rent - df.Price) / df.fair_rent
    df["deal_%"] = (raw_gap * 100).round(1)   # + = cheaper than the ML fair rent
    f = pd.DataFrame(index=df.index)
    f["price_ratio"] = df.Price / budget_max
    f["deal_gap"] = raw_gap
    f["size_gap"] = (df.Sqft - target).abs() / target
    f["bed_extra"] = df.Bed - min_bed
    f["bath"] = df.Bath
    f["km"] = km
    f["travel_ratio"] = df.travel_cost / budget_max
    for n in FEATURE_NAMES:
        df["f_" + n] = f[n].astype(float)
    return df


def rank(df, max_km=None, w_value=5, w_space=3, w_commute=5, w_savings=2, top_n=10, max_per_block=3,
         use_ranker=True, ml_weight=0.5):
    """Score and sort a prepared pool. Weights are 0-10 sliders."""
    if df.empty:
        return df
    df = df.copy()
    f = df[["f_" + n for n in FEATURE_NAMES]].rename(columns=lambda c: c[2:])
    use_commute = bool(df.dist_source.notna().any()) and w_commute > 0
    cap = max_km or max(float(f.km.max()), 1.0)
    weights = {"w_value": w_value, "w_space": w_space, "w_commute": w_commute, "w_savings": w_savings}
    df["baseline"] = baseline_from_features(f, cap=cap, use_commute=use_commute, weights=weights)

    ranker = load_ranker() if use_ranker else None
    if ranker is not None:
        raw = ranker["model"].decision_function(f[ranker["features"]].values / ranker["scale"])
        df["ml_fit"] = pd.Series(raw, index=df.index).rank(pct=True) * 100
        df["score"] = (1 - ml_weight) * df.baseline + ml_weight * df.ml_fit
    else:
        df["ml_fit"] = np.nan
        df["score"] = df.baseline
    df["baseline"], df["score"] = df.baseline.round(1), df.score.round(1)

    df = df.sort_values("score", ascending=False)
    df = df.groupby(df.Place + "|" + df.Sub, sort=False).head(max_per_block)  # not ten flats from one block
    df = df.head(top_n).copy()
    df["why"] = df.apply(_explain, axis=1)
    df["details"] = df.apply(lambda r: listing_logic.facility_text(r.to_dict()), axis=1)
    df["address_label"] = [listing_logic.address_label(a, src) for a, src in zip(df.address, df.address_source)]
    return df


def recommend(budget_max, max_km=None, w_value=5, w_space=3, w_commute=5, w_savings=2, top_n=10,
              max_per_block=3, use_ranker=True, ml_weight=0.5, **prepare_kwargs):
    """prepare() then rank() in one call. Extra keyword arguments go to prepare()."""
    pool = prepare(budget_max, max_km=max_km, **prepare_kwargs)
    return rank(pool, max_km=max_km, w_value=w_value, w_space=w_space, w_commute=w_commute,
                w_savings=w_savings, top_n=top_n, max_per_block=max_per_block, use_ranker=use_ranker,
                ml_weight=ml_weight)


def _explain(r):
    bits = []
    if r["deal_%"] >= 35:
        bits.append(f"{r['deal_%']:.0f}% below typical asking rent - unusually cheap, verify before visiting")
    elif r["deal_%"] >= 5:
        bits.append(f"{r['deal_%']:.0f}% below typical asking rent for similar flats")
    elif r["deal_%"] <= -5:
        bits.append(f"{abs(r['deal_%']):.0f}% above typical asking rent for similar flats")
    else:
        bits.append("priced near typical asking rent")
    bits.append(f"{r.Sqft:.0f} sqft")
    if not np.isnan(r.km):
        bits.append(f"{r.km:.1f} km " + ("by road" if r.dist_source in ("osrm", "google") else "(estimated)"))
    if not np.isnan(r.ml_fit):
        bits.append(f"learned fit {r.ml_fit:.0f}/100")
    return ", ".join(bits)


def feature_dict(row):
    """Feature values of one flat, as saved with a survey answer."""
    return {n: (0.0 if pd.isna(row["f_" + n]) else float(row["f_" + n])) for n in FEATURE_NAMES}
