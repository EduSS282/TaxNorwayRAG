"""Supported response languages; evidence remains in its original language."""

from typing import Literal

ResponseLanguage = Literal["en", "nb", "es"]
LANGUAGE_NAMES: dict[ResponseLanguage, str] = {
    "en": "English",
    "nb": "Norwegian Bokmål",
    "es": "Spanish",
}
