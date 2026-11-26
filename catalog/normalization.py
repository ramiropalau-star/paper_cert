"""Catalog text normalization shared by classification and seed data."""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_catalog_text(value: str) -> str:
    """Normalize text with NFKC, casefold, and whitespace collapse.

    Accents are preserved on purpose: the catalog stores exact aliases, and
    matching is intentionally exact rather than fuzzy or accent-insensitive.
    """
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def normalize_alias_text(value: str) -> str:
    """Fold alias/label text for matching: NFKD, accent and typographic
    dash/quote folding, casefold, whitespace collapse."""
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    folded = folded.replace("‐", "-").replace("‑", "-").replace("‒", "-")
    folded = folded.replace("–", "-").replace("—", "-").replace("−", "-")
    folded = folded.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return _WHITESPACE.sub(" ", folded).strip().casefold()
