from hashlib import sha256

import pytest

from taxguide.ingestion.hashing import canonical_source_url, document_id_from_url, hash_text


def test_hash_text_is_deterministic():
    assert hash_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_document_id_is_deterministic():
    assert document_id_from_url("https://example.com/a") == document_id_from_url(
        "https://example.com/a"
    )


def test_document_id_changes_for_different_urls():
    assert document_id_from_url("https://example.com/a") != document_id_from_url(
        "https://example.com/b"
    )


def test_canonicalization_preserves_meaningful_components():
    assert document_id_from_url("https://EXAMPLE.com:443/a#part") == document_id_from_url(
        "https://example.com/a"
    )
    assert document_id_from_url("https://example.com/a?q=1") != document_id_from_url(
        "https://example.com/a?q=2"
    )
    assert document_id_from_url("https://example.com/a/") != document_id_from_url(
        "https://example.com/a"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTP://EXAMPLE.COM:80", "http://example.com/"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com:0/a", "https://example.com:0/a"),
        ("https://[2001:DB8::1]:443/a#part", "https://[2001:db8::1]/a"),
        ("https://[::1]:8443/a", "https://[::1]:8443/a"),
        ("https://example.com/A%2Fb?b=2&a=1", "https://example.com/A%2Fb?b=2&a=1"),
    ],
)
def test_canonical_source_url(url, expected):
    assert canonical_source_url(url) == expected
    assert canonical_source_url(expected) == expected


@pytest.mark.parametrize(
    "url",
    [
        "/relative/path",
        "ftp://example.com/a",
        "https:///missing-host",
        "https://user:password@example.com/a",
        "https://:password@example.com/a",
        "https://@example.com/a",
        "https://example.com:invalid/a",
        "https://example.com:65536/a",
    ],
)
def test_invalid_source_url_is_rejected(url):
    with pytest.raises(ValueError):
        document_id_from_url(url)


def test_explicit_zero_port_has_distinct_document_id():
    assert document_id_from_url("https://example.com:0/a") != document_id_from_url(
        "https://example.com/a"
    )


def test_hash_text_uses_utf8_without_changing_content():
    text = "Skatt på lønn\n"

    assert hash_text(text) == sha256(text.encode("utf-8")).hexdigest()
    assert hash_text(text) == hash_text(text)
    assert hash_text(text) != hash_text(text.rstrip())
