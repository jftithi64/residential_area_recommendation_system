"""Small pure helpers for flat cards and the fair-rent page (no Streamlit here, so they are easy to test)."""
import re
from datetime import date

import pandas as pd


def phone_links(contact):
    """Call and WhatsApp links if `contact` is a Bangladesh mobile number, else None."""
    digits = re.sub(r"\D", "", str(contact or ""))
    if digits.startswith("880"):
        digits = "0" + digits[3:]
    if re.fullmatch(r"01[3-9]\d{8}", digits):
        return {"shown": digits, "tel": f"tel:+88{digits}", "wa": f"https://wa.me/88{digits}"}
    return None


def deal_badge(deal_pct):
    """(text, pill kind) comparing the rent with the typical asking rent, or None if unknown."""
    if deal_pct is None or pd.isna(deal_pct):
        return None
    if deal_pct >= 35:
        return "Unusually cheap: check it before you visit", "warn"
    if deal_pct >= 5:
        return f"{deal_pct:.0f}% below typical rent", "good"
    if deal_pct <= -5:
        return f"{abs(deal_pct):.0f}% above typical rent", "warn"
    return "Near typical rent", "info"


def freshness(is_extra, updated_at, listed_at, today=None):
    """(text, pill kind): how recently a person confirmed this flat. Dataset rows were never confirmed."""
    if not is_extra or pd.isna(is_extra):
        return "Not confirmed (public dataset)", "muted"
    stamp = next((x for x in (updated_at, listed_at) if x is not None and not pd.isna(x)), None)
    d = pd.to_datetime(stamp, errors="coerce")
    if pd.isna(d):
        return "Owner listing", "info"
    days = (pd.Timestamp(today or date.today()) - d).days
    label = "Confirmed today" if days <= 0 else f"Confirmed {days} day{'s' if days != 1 else ''} ago"
    return label, ("good" if days <= 14 else "warn")


def fair_verdict(rent, fair, error_pct):
    """(gap %, sentence, pill kind). Gaps smaller than the model's own typical error are called normal."""
    gap = (rent - fair) / fair * 100
    if abs(gap) <= error_pct:
        return gap, "Within the normal range for similar flats.", "info"
    if gap < 0:
        return gap, ("Lower than similar flats. Good news, but ask why: floor, condition or missing "
                     "facilities may explain it."), "good"
    if gap <= 2 * error_pct:
        return gap, "Higher than similar flats. You can use this to negotiate.", "warn"
    return gap, "Much higher than similar flats. Compare with other flats before you agree.", "warn"
