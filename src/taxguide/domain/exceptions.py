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


class CrawlerError(TaxguideError):
    """Base error for safe remote document acquisition."""


class DisallowedDomainError(CrawlerError):
    pass


class RobotsDisallowedError(CrawlerError):
    pass


class UnsupportedContentTypeError(CrawlerError):
    pass


class FetchError(CrawlerError):
    pass


class ResponseTooLargeError(FetchError):
    pass


class CorpusError(TaxguideError):
    """A manifest-driven corpus build could not complete safely."""


class EmbeddingError(TaxguideError):
    """An embedding provider returned an unusable result or could not be reached."""


class VectorStoreError(TaxguideError):
    """A vector-store request was rejected or could not be completed."""
