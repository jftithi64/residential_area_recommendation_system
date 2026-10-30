"""Vehicle types and their fare rates, so the travel cost is worked out from the distance automatically.

Fare for one one-way trip = max(minimum fare, base fare + km x rate per km). Walking is free.
All numbers are ESTIMATES of typical Dhaka fares (BDT), not official tariffs. Rickshaw, CNG and ride-hailing
prices are negotiated or change with demand, and bus and metro fares are revised by the government.
The Find page lets the person change any rate, so edit DEFAULT_MODES here to change the starting values.

metro: fare is Tk 5/km, minimum Tk 20 (MRT Line-6, Uttara North - Motijheel, 2022 tariff). The metro only runs along
that one line, so use it only if both the flat and the destination are near a station.
"""
import numpy as np

# code -> label, rate per km, base fare, minimum fare, short note. Order here is the order in the drop-down.
DEFAULT_MODES = {
    "bus":      {"label": "Bus",                   "per_km": 2.45,  "base": 0.0,  "min_fare": 10.0,
                 "note": "Local bus / minibus. Government rate per km, minimum Tk 10."},
    "metro":    {"label": "Metro rail",            "per_km": 5.0,   "base": 0.0,  "min_fare": 20.0,
                 "note": "MRT Line-6 only (Uttara North to Motijheel). Tk 5 per km, minimum Tk 20."},
    "rickshaw": {"label": "Rickshaw",              "per_km": 15.0,  "base": 0.0,  "min_fare": 20.0,
                 "note": "Negotiated; usually Tk 15 to 25 per km. Best for short trips."},
    "cng":      {"label": "CNG auto-rickshaw",     "per_km": 18.0,  "base": 22.0, "min_fare": 50.0,
                 "note": "Metered. About Tk 40 to 50 for the first 2 km, then about Tk 18 per km."},
    "bike":     {"label": "Ride-share bike",       "per_km": 18.0,  "base": 15.0, "min_fare": 50.0,
                 "note": "Pathao / Uber style motorbike ride."},
    "car":      {"label": "Ride-share car",        "per_km": 32.0,  "base": 40.0, "min_fare": 120.0,
                 "note": "Uber / Pathao style car ride. Rises in traffic and rain."},
    "own_bike": {"label": "My own motorbike",      "per_km": 4.0,   "base": 0.0,  "min_fare": 0.0,
                 "note": "Fuel only (about Tk 4 per km). Parking and servicing not included."},
    "walk":     {"label": "Walk",                  "per_km": 0.0,   "base": 0.0,  "min_fare": 0.0,
                 "note": "Free."},
    "custom":   {"label": "Custom (my own rate)",  "per_km": 5.0,   "base": 0.0,  "min_fare": 0.0,
                 "note": "Type your own fare per km, as before."},
}
DEFAULT_MODE = "bus"


def label(code):
    return DEFAULT_MODES[code]["label"]


def rates_for(code, per_km=None, base=None, min_fare=None):
    """The rates of one vehicle, with any of the three overridden (None keeps the default)."""
    d = DEFAULT_MODES[code]
    return {"per_km": d["per_km"] if per_km is None else float(per_km),
            "base": d["base"] if base is None else float(base),
            "min_fare": d["min_fare"] if min_fare is None else float(min_fare)}


def one_way_fare(km, code=DEFAULT_MODE, per_km=None, base=None, min_fare=None):
    """Fare of ONE one-way trip of km kilometres by this vehicle, in BDT. km can be a number or an array.
    Unknown distances (NaN) stay NaN. Walking is always 0."""
    r = rates_for(code, per_km, base, min_fare)
    km = np.asarray(km, dtype=float)
    fare = np.maximum(r["min_fare"], r["base"] + km * r["per_km"])
    if code == "walk" or r["per_km"] == 0 and r["base"] == 0 and r["min_fare"] == 0:
        fare = np.zeros_like(km)
    out = np.where(np.isnan(km), np.nan, fare)
    return float(out) if out.ndim == 0 else out
