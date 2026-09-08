class TaxguideError(Exception):
    """Base error safe to present at the application boundary."""


class DocumentLoadError(TaxguideError):
    pass


class UnsupportedDocumentError(TaxguideError):
    pass


class ParseError(TaxguideError):
    pass


class EmptyDocumentError(ParseError):
    pass


class InvalidConfigurationError(TaxguideError):
    pass
