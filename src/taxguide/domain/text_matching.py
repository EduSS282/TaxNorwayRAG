"""Shared literal matching for deterministic multilingual tax rules."""

import re
import unicodedata


def normalize_query(value: str) -> str:
    """Normalize typography and common Spanish accent omissions, not word stems."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans("áéíóúü", "aeiouu"))
    value = re.sub(r"[‐‑‒–—−-]", " ", value)
    value = value.replace("’", "'")
    return " ".join(value.split())


def contains_term(text: str, term: str) -> bool:
    """Match whole words/phrases; do not let 'tax' match 'syntax' or 'taxi'."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.UNICODE) is not None
