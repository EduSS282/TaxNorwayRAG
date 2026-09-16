from enum import StrEnum


class ParagraphKind(StrEnum):
    TEXT = "text"
    LIST = "list"
    TABLE = "table"


class PageType(StrEnum):
    STATIC_ARTICLE = "static_article"
    INTERACTIVE_WIZARD = "interactive_wizard"
    UNKNOWN_DYNAMIC = "unknown_dynamic"


class TaxTopic(StrEnum):
    """Stable identifiers for the controlled Norwegian individual-tax taxonomy."""

    INCOME = "income"
    EMPLOYMENT = "employment"
    PENSION = "pension"
    BANK = "bank"
    LOAN = "loan"
    WEALTH = "wealth"
    PROPERTY = "property"
    FOREIGN_INCOME = "foreign_income"
    FOREIGN_ASSETS = "foreign_assets"
    DEDUCTIONS = "deductions"
    COMMUTING = "commuting"
    FAMILY = "family"
    SHARES = "shares"
    CRYPTO = "crypto"
    SELF_EMPLOYED = "self_employed"
    PAYE = "paye"
    TAX_RESIDENCY = "tax_residency"
    DEADLINES = "deadlines"
    APPEALS = "appeals"
