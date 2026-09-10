from enum import StrEnum


class ParagraphKind(StrEnum):
    TEXT = "text"
    LIST = "list"
    TABLE = "table"


class PageType(StrEnum):
    STATIC_ARTICLE = "static_article"
    INTERACTIVE_WIZARD = "interactive_wizard"
    UNKNOWN_DYNAMIC = "unknown_dynamic"
