"""Turn the strings the model copies off the page into Python values."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from dateutil import parser as dateparser


def parse_amount(value) -> Decimal | None:
    """Parse printed amounts without introducing binary floating-point error."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = re.sub(r"(?i)rs\.", "", str(value).replace("₹", "").replace("INR", ""))
    cleaned = cleaned.replace(",", "").replace("/-", "").strip()
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(lakh|lakhs|crore|crores)?", cleaned, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid amount: {value!r}")
    amount = Decimal(match.group(1))
    multiplier = (match.group(2) or "").lower()
    if multiplier.startswith("lakh"):
        amount *= Decimal(100000)
    elif multiplier.startswith("crore"):
        amount *= Decimal(10000000)
    return amount


def parse_date(value, dayfirst: bool = True) -> date | None:
    """Parse Indian dates day-first; callers use month-first for US vendors."""
    if not value:
        return None
    return dateparser.parse(str(value), dayfirst=dayfirst, yearfirst=False).date()
