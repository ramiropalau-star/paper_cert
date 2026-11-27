"""Multilingual month-name lookup for date parsing.

Month names are folded (NFKD, accents stripped, casefolded) so "Setembre",
"septiembre" and "September" all resolve. The map covers the languages
certificates actually arrive in; abbreviations are included only where the
folded form is unambiguous in a date context.
"""

from __future__ import annotations

import re
import unicodedata


def _build_month_names() -> dict[str, int]:
    """Merge per-language tables; identical cross-language names collapse,
    conflicting ones are a bug and fail at import time."""
    languages = (
        # Catalan
        {
            "gener": 1,
            "febrer": 2,
            "març": 3,
            "abril": 4,
            "maig": 5,
            "juny": 6,
            "juliol": 7,
            "agost": 8,
            "setembre": 9,
            "octubre": 10,
            "novembre": 11,
            "desembre": 12,
        },
        # Spanish
        {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        },
        # English
        {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        },
        # French
        {
            "janvier": 1,
            "février": 2,
            "mars": 3,
            "avril": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7,
            "août": 8,
            "septembre": 9,
            "octobre": 10,
            "novembre": 11,
            "décembre": 12,
        },
        # German
        {
            "januar": 1,
            "februar": 2,
            "märz": 3,
            "april": 4,
            "mai": 5,
            "juni": 6,
            "juli": 7,
            "august": 8,
            "september": 9,
            "oktober": 10,
            "november": 11,
            "dezember": 12,
        },
        # Portuguese
        {
            "janeiro": 1,
            "fevereiro": 2,
            "março": 3,
            "abril": 4,
            "maio": 5,
            "junho": 6,
            "julho": 7,
            "agosto": 8,
            "setembro": 9,
            "outubro": 10,
            "novembro": 11,
            "dezembro": 12,
        },
        # Italian
        {
            "gennaio": 1,
            "febbraio": 2,
            "marzo": 3,
            "aprile": 4,
            "maggio": 5,
            "giugno": 6,
            "luglio": 7,
            "agosto": 8,
            "settembre": 9,
            "ottobre": 10,
            "novembre": 11,
            "dicembre": 12,
        },
        # Abbreviations.
        {
            "ene": 1,
            "ene.": 1,
            "jan": 1,
            "gen": 1,
            "janv": 1,
            "janv.": 1,
            "feb": 2,
            "fev": 2,
            "fevr": 2,
            "mar": 3,
            "abr": 4,
            "may": 5,
            "mai": 5,
            "mag": 5,
            "jun": 6,
            "jui": 6,
            "giu": 6,
            "jul": 7,
            "juil": 7,
            "lug": 7,
            "ago": 8,
            "aug": 8,
            "sep": 9,
            "sept": 9,
            "set": 9,
            "oct": 10,
            "ott": 10,
            "out": 10,
            "nov": 11,
            "dic": 12,
            "des": 12,
            "dez": 12,
            "dec": 12,
        },
    )
    table: dict[str, int] = {}
    for names in languages:
        for name, number in names.items():
            previous = table.setdefault(name, number)
            if previous != number:
                raise ValueError(f"Conflicting month number for {name!r}: {previous} vs {number}")
    return table


_MONTH_NAMES = _build_month_names()


def _fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(folded.casefold().split())


MONTH_NUMBERS: dict[str, int] = {_fold(name).rstrip("."): num for name, num in _MONTH_NAMES.items()}

# The pattern must match accented surface forms ("décembre", "März") as
# well as folded ones, so both spellings of every name are alternatives.
_PATTERN_NAMES = set()
for _name in _MONTH_NAMES:
    _PATTERN_NAMES.add(_name)
    _PATTERN_NAMES.add(_fold(_name).rstrip("."))
_PATTERN_NAMES.discard("")

# Longest names first so the regex prefers "septiembre" over "sep".
_MONTH_PATTERN = "|".join(re.escape(name) for name in sorted(_PATTERN_NAMES, key=len, reverse=True))
MONTH_TOKEN = rf"(?:{_MONTH_PATTERN})"
MONTH_NAME_RE = re.compile(rf"(?<![A-Za-zÀ-ÿ])(?:{_MONTH_PATTERN})(?![A-Za-zÀ-ÿ])", re.IGNORECASE)

_CONNECTOR = r"(?:\s+(?:de|d['’]|of|del|al)\s*|\s+)"

# "18 Setembre 2026", "18 de septiembre de 2026", "5 décembre 2020"
DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\.?{_CONNECTOR}({MONTH_TOKEN})\b\.?"
    rf"{_CONNECTOR}(\d{{4}})\b",
    re.IGNORECASE,
)
# "September 18, 2026", "Setembre 18 del 2026"
MONTH_DAY_YEAR_RE = re.compile(
    rf"\b({MONTH_TOKEN})\b\.?{_CONNECTOR}(\d{{1,2}})(?:st|nd|rd|th)?\.?,?"
    rf"{_CONNECTOR}(\d{{4}})\b",
    re.IGNORECASE,
)
# "SEPTIEMBRE 2020" — month + year only, kept as ambiguous evidence.
MONTH_YEAR_RE = re.compile(
    rf"\b({MONTH_TOKEN})\b\.?{_CONNECTOR}(\d{{4}})\b",
    re.IGNORECASE,
)


def month_number(token: str) -> int | None:
    """Return the month number for a (possibly accented) month name."""
    return MONTH_NUMBERS.get(_fold(token).rstrip("."))
