import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from dateutil import parser as dateparser


def _ascii_digits(value: str) -> str:
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value)


def _number(value: str) -> int | float:
    match = re.fullmatch(
        r"\s*(?:Rs\.?|INR|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*"
        r"(k|lakhs?|lacs?|crores?|million|m)?\s*(?:rupees|INR|%|percent|years?|yrs?)?\s*",
        value, re.IGNORECASE,
    )
    if not match:
        raise ValueError("Numeric conversion requires an explicit digit-written value; number words are unsupported")
    number = Decimal(match[1].replace(",", ""))
    unit = (match[2] or "").lower()
    if unit == "k":
        number *= 1000
    elif unit.startswith(("lakh", "lac")):
        number *= 100000
    elif unit.startswith("crore"):
        number *= 10000000
    elif unit in ("m", "million"):
        number *= 1000000
    return int(number) if number == number.to_integral_value() else float(number)


def transform_output(value: str, transform: str, language: str | None = None) -> str | int | float:
    if transform in ("roman_text", "english_text"):
        non_english = language and language.lower().split("-")[0].split("_")[0] not in ("en", "english")
        if not value.isascii() or (transform == "english_text" and non_english):
            action = "Translation" if transform == "english_text" else "Transliteration"
            raise ValueError(f"{action} is unsupported in this English-first scenario; original text is retained in the extracted field")
        return value
    value = _ascii_digits(value.strip())
    if transform == "pan_last_four":
        compact = re.sub(r"\s+", "", value).upper()
        if not re.fullmatch(r"(?:[A-Z]{5}[0-9])?[0-9]{3}[A-Z]", compact):
            raise ValueError("PAN suffix requires a full PAN or its last four characters (three digits and one letter)")
        return compact[-4:]
    if transform == "date_dmy":
        if not re.fullmatch(
            r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2}|"
            r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4})", value
        ):
            raise ValueError("DOB normalization requires an explicitly stated full date with a four-digit year")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date = datetime.strptime(value, "%Y-%m-%d")
        else:
            date = dateparser.parse(value, dayfirst=True, fuzzy=False)
        return date.strftime("%d/%m/%Y")
    if transform == "months":
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(months?|mos?|years?|yrs?)", value, re.IGNORECASE)
        if not match:
            raise ValueError("Tenure conversion requires a digit-written duration with months or years")
        months = Decimal(match[1]) * (12 if match[2].lower().startswith(("year", "yr")) else 1)
        if months != months.to_integral_value():
            raise ValueError("Tenure does not resolve to a whole number of months")
        return int(months)
    if transform == "number":
        return _number(value)
    if transform == "percent":
        return f"{_number(value)}%"
    raise ValueError(f"Unsupported output transform '{transform}'")
