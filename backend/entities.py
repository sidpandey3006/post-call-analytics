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


ID_DEFAULT = r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9][A-Z0-9-]{4,19}\b"
NAME_CUES = (r"(?i:my name is|my name's|this is|i am|i'm|speaking with|speaking to|call me|name is|name's|"
             r"asking for|ask for|hello|hi|dear)")
NAME_RE = re.compile(NAME_CUES + r"\s+(?:(?:Mr|Mrs|Ms|Miss|Dr|Mx)\.?\s+)?([A-Z][a-z]+(?:[ '-][A-Z][a-z]+){0,2})")
NAME_STOP = {"Sorry", "Calling", "Happy", "Glad", "Not", "Sure", "Fine", "Good", "Great", "Looking", "Here", "Afraid",
             "Thank", "Thanks", "Okay", "Yes", "No", "Please", "Just", "Still", "Having", "Trying", "Interested"}
HINDI_NAME_WORD = r"[\u0900-\u0963\u0970-\u097f]+"
HINDI_NAME_PATTERNS = [
    re.compile(r"(?:मेरा नाम|नाम है)\s+(" + HINDI_NAME_WORD + r"(?:\s+" + HINDI_NAME_WORD + r"){0,2}?)(?=\s+है|[।,;!?\n]|$)"),
    re.compile(r"(" + HINDI_NAME_WORD + r"(?:\s+" + HINDI_NAME_WORD + r"){0,2})\s+जी(?=\s|[।,;!?]|$)"),
]
HINDI_NAME_STOP = {"हाँ", "हां", "नहीं", "सर", "मैडम", "जी", "ओके", "बिलकुल"}
MAX_CANDIDATES = 50
_NESTED_QUANT = re.compile(r"\([^)]*[+*][^)]*\)[+*{]")


class PatternError(ValueError):
    pass


def compile_id_pattern(pattern: str | None) -> re.Pattern:
    p = (pattern or "").strip() or ID_DEFAULT
    if len(p) > 200 or _NESTED_QUANT.search(p):
        raise PatternError("ID pattern is too long or has nested repetition; simplify it")
    try:
        return re.compile(p)
    except re.error as e:
        raise PatternError(f"Invalid ID pattern: {e}")


def _find_names(text: str) -> list[str]:
    out = []
    for m in NAME_RE.finditer(text):
        words = [w for w in re.split(r"[ ]", m.group(1)) if w and w not in NAME_STOP]
        if words:
            out.append(" ".join(words))
    for pattern in HINDI_NAME_PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(1).strip()
            if not any(word in HINDI_NAME_STOP for word in value.split()):
                out.append(value)
    return out


def _find_text(text: str) -> list[str]:
    out: list[str] = _find_names(text)
    for clause in re.split(r"[;!?\n\u0964\u0965]|\.(?=\s|$)", text):
        clause = clause.strip(" \t,")
        if not clause:
            continue
        # Keep both complete responses and verbatim values after common spoken cues.
        cue = re.search(
            r"(?i)\b(?:my name is|my name's|i am|i'm|i live in|i work (?:at|for)|"
            r"(?:name|profession|occupation|company|current (?:address|city)|permanent (?:address|city))"
            r"\s*(?:is|:))\s+(.+)", clause)
        if cue:
            value = cue.group(1).strip()
            out.append(re.split(r"(?i),?\s+(?:pincode|pin code|PIN)\b", value)[0].rstrip(", "))
        if len(clause) <= 120:
            out.append(clause)
        if re.search(r"[\u0900-\u097f]", clause):
            out.extend(part.strip() for part in clause.split(",") if 0 < len(part.strip()) <= 120)
    return out


def find_candidates(entity_type: str, text: str, pattern: str | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if entity_type == "name":
        matches = _find_names(text)
    elif entity_type == "text" and not (pattern or "").strip():
        matches = _find_text(text)
    elif entity_type in ("id", "text"):
        rx = compile_id_pattern(pattern)
        matches = [(m.group(1) if entity_type == "text" and rx.groups else m.group(0)) or ""
                   for m in rx.finditer(text)]
    else:
        matches = PATTERNS[entity_type].findall(text)
    for m in matches:
        span = m.strip()
        if len(out) >= MAX_CANDIDATES:
            break
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
    if entity_type in ("id", "name", "text"):
        return value.strip()
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
