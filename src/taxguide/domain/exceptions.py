class TaxguideError(Exception):
    """Base error safe to present at the application boundary."""


class DocumentLoadError(TaxguideError):
    pass


class UnsupportedDocumentError(TaxguideError):
    """No parser supports the document's source or format."""


class ParseError(TaxguideError):
    """A supported document could not be parsed into usable content."""


class EmptyDocumentError(ParseError):
    """Parsing a supported document produced no substantive content."""


class InvalidConfigurationError(TaxguideError):
    pass
