"""Regex candidate finders (tuned to over-find) and verbatim-value normalizers."""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import phonenumbers
from dateutil import parser as dateparser

NONE = "none"

PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\(?\+?\d[\d\s()\-.]{6,}\d"),
    "amount": re.compile(
        r"(?:[$€£₹¥]|Rs\.?|INR|USD|EUR|GBP)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|K|lakh|lakhs|million|M))?"
        r"|\d[\d,]*(?:\.\d+)?\s?(?:dollars|rupees|euros|pounds|USD|INR|EUR|GBP)"
    ),
    "date": re.compile(
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
        r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s\d{1,2}(?:st|nd|rd|th)?(?:,?\s\d{4})?\b"
        r"|\b\d{1,2}(?:st|nd|rd|th)?\s(?:of\s)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*(?:,?\s\d{4})?\b"
        r"|\b(?:next|this)\s(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b"
        r"|\b(?:tomorrow|today|next week|next month)\b",
        re.IGNORECASE,
    ),
}


def find_candidates(entity_type: str, text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in PATTERNS[entity_type].findall(text):
        span = m.strip()
        if entity_type == "phone" and sum(c.isdigit() for c in span) < 7:
            continue
        if span and span not in seen:
            seen.add(span)
            out.append(span)
    return out


def normalize_entity(entity_type: str, value: str, reference: datetime | None = None, region: str | None = None):
    """Return a normalized value, or None if it cannot be normalized."""
    if value is None or value == NONE:
        return None
    if entity_type == "email":
        return value.lower()
    if entity_type == "phone":
        try:
            parsed = phonenumbers.parse(value, region)
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return re.sub(r"[^\d+]", "", value)
    if entity_type == "amount":
        digits = re.search(r"\d[\d,]*(?:\.\d+)?", value)
        if not digits:
            return None
        try:
            num = Decimal(digits.group().replace(",", ""))
        except InvalidOperation:
            return None
        low = value.lower()
        if re.search(r"\d\s?k\b", low):
            num *= 1000
        elif "lakh" in low:
            num *= 100000
        elif re.search(r"\d\s?(m|million)\b", low):
            num *= 1_000_000
        currency = next((c for s, c in (("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("₹", "INR"), ("rs", "INR"),
                                         ("rupee", "INR"), ("usd", "USD"), ("eur", "EUR"), ("gbp", "GBP"),
                                         ("inr", "INR"), ("dollar", "USD")) if s in low), None)
        return {"amount": str(num), "currency": currency}
    if entity_type == "date":
        try:
            return dateparser.parse(value, default=reference or datetime.now()).date().isoformat()
        except (ValueError, OverflowError):
            return None  # relative phrases ("next week") stay raw for the caller to resolve
    return None
