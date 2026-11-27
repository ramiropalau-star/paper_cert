"""Conservative cleaning of embedded PDF text before storage.

Only unambiguous repairs are applied: unicode normalization, control
character stripping and whitespace collapsing. Stored text must stay faithful
to the document so evidence quotes remain traceable; anything that cannot be
repaired reliably is left untouched.
"""

from __future__ import annotations

import re
import unicodedata

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_WS_RE = re.compile(r"[ \t]+")

# Explicit repairs for artifacts observed in real embedded text layers.
# Add an entry only when the corruption is unambiguous; never guess.
_REPAIRS: dict[str, str] = {}


def clean_embedded_text(text: str) -> str:
    """Normalize embedded page text without altering its content."""
    if not text:
        return text
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _REPAIRS.items():
        text = text.replace(bad, good)
    text = _CONTROL_RE.sub("", text)
    lines = [_HORIZONTAL_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
