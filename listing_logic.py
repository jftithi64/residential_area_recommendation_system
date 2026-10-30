"""Rules for flats that people add: validation, edit codes, and helpers shared by the pages and the job."""
import hashlib
import hmac
import secrets

import numpy as np

from common import AREA_COORDS, PPSF_RANGE, PRICE_RANGE, SQFT_RANGE

TENANT_RULES = {"any": "Anyone", "family": "Family only", "bachelor_male": "Bachelor (male)",
                "bachelor_female": "Bachelor (female)"}
FAR_FROM_FAIR = 0.40   # a rent this far from the model's typical rent is held for a closer look
STALE_DAYS = 45
# Limits for what a person may submit. Looser than the training-data cleaning limits in common.py:
# there is no meaningful minimum rent here, only a guard against typing errors.
LISTING_PRICE_MIN = 1000
LISTING_PPSF_MIN = 2
MAX_ROOMS = 10


def make_edit_code():
    """A private code the owner uses to edit or remove the listing. Shown once, only a salted hash is stored."""
    return secrets.token_urlsafe(10)


def hash_code(code, salt=None):
    """'salt$digest' (PBKDF2-SHA256). Every listing gets its own salt, so equal codes have different hashes."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", code.strip().encode("utf-8"), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${digest}"


def check_code(code, stored_hash):
    if not stored_hash:
        return False
    code = (code or "").strip()
    if "$" in stored_hash:
        salt = stored_hash.split("$", 1)[0]
        return hmac.compare_digest(hash_code(code, salt), stored_hash)
    # listings made by the first version stored a plain SHA-256; keep them working
    return hmac.compare_digest(hashlib.sha256(code.encode("utf-8")).hexdigest(), stored_hash)


def validate(place, sqft, bed, bath, price, known_places, fair_rent=None):
    """Return (errors, flags). Errors stop the submission; flags send it to the admin for a closer look."""
    errors, flags = [], []
    if place not in known_places:
        errors.append("Choose an area from the list.")
    if not (SQFT_RANGE[0] <= sqft <= SQFT_RANGE[1]):
        errors.append(f"Size must be between {SQFT_RANGE[0]} and {SQFT_RANGE[1]} sqft.")
    if not (LISTING_PRICE_MIN <= price <= PRICE_RANGE[1]):
        errors.append(f"Rent must be between ৳{LISTING_PRICE_MIN:,} and ৳{PRICE_RANGE[1]:,} per month.")
    if bed < 1 or bath < 1:
        errors.append("Bedrooms and bathrooms must be at least 1.")
    if bed > MAX_ROOMS or bath > MAX_ROOMS:
        errors.append(f"Bedrooms and bathrooms can be at most {MAX_ROOMS}.")
    if sqft > 0 and not errors:
        ppsf = price / sqft
        if not (LISTING_PPSF_MIN <= ppsf <= PPSF_RANGE[1]):
            errors.append(f"A rent of ৳{ppsf:.0f} per sqft is outside the usual range "
                          f"(৳{LISTING_PPSF_MIN}-{PPSF_RANGE[1]}). Check the size and the rent.")
        elif sqft / bed < 80:
            flags.append(f"only {sqft / bed:.0f} sqft per bedroom")
    if fair_rent and not errors:
        gap = (price - fair_rent) / fair_rent
        if abs(gap) > FAR_FROM_FAIR:
            flags.append(f"rent is {abs(gap) * 100:.0f}% {'above' if gap > 0 else 'below'} typical asking rent "
                         f"for similar flats (৳{fair_rent:,.0f})")
    return errors, flags


def facility_text(r):
    """One line describing what is known about a flat's details; empty for dataset rows."""
    def has(v):
        return v is not None and not (isinstance(v, float) and np.isnan(v))
    parts = []
    rule = r.get("tenant_rule")
    if isinstance(rule, str) and rule in TENANT_RULES and rule != "any":
        parts.append(TENANT_RULES[rule])
    if has(r.get("floor")):
        parts.append(f"floor {int(r['floor'])}")
    for key, label in (("lift", "lift"), ("gas", "gas"), ("parking", "parking"), ("generator", "generator"),
                       ("furnished", "furnished")):
        if has(r.get(key)) and int(r[key]) == 1:
            parts.append(label)
    if isinstance(r.get("available_from"), str) and r["available_from"]:
        parts.append(f"available from {r['available_from']}")
    return ", ".join(parts)


def address_label(address, source):
    """The address as shown to people. (Demo addresses are no longer labelled on screen; address_source still records them.)"""
    if not isinstance(address, str) or not address.strip():
        return ""
    return address


def area_names():
    return sorted(AREA_COORDS)
