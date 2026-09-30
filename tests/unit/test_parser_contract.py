"""Parser consumers can handle failures without depending on a source adapter."""

import pytest

from taxguide.domain.exceptions import (
    EmptyDocumentError,
    ParseError,
    TaxguideError,
    UnsupportedDocumentError,
)


@pytest.mark.parametrize("error_type", [ParseError, EmptyDocumentError, UnsupportedDocumentError])
def test_parser_failures_are_application_errors(error_type):
    with pytest.raises(TaxguideError, match="document diagnostic"):
        raise error_type("document diagnostic")


def test_empty_content_can_be_handled_as_parse_failure():
    with pytest.raises(ParseError, match="No substantive content"):
        raise EmptyDocumentError("No substantive content")


def test_unsupported_document_is_distinct_from_parse_failure():
    assert not isinstance(UnsupportedDocumentError("Unsupported format"), ParseError)
