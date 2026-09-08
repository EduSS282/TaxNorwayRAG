from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from taxguide.domain.exceptions import DocumentLoadError
from taxguide.domain.models import RawDocument
from taxguide.sources.local import LocalHtmlSource


def test_byte_hash_and_original_url(tmp_path):
    data = b"\xef\xbb\xbf<main>\r\n<p>Text</p></main>"
    path = tmp_path / "page.html"
    path.write_bytes(data)
    url = "https://www.skatteetaten.no:443/en/example#part"
    raw = LocalHtmlSource().load(path, url)
    assert raw.content_hash == sha256(data).hexdigest()
    assert raw.source_url == url
    assert raw.retrieved_at.tzinfo is not None
    assert raw.local_path == path.resolve()
    assert raw.content == "<main>\r\n<p>Text</p></main>"
    assert raw.content_type == "text/html"


def test_missing_file_and_invalid_encoding(tmp_path):
    path = tmp_path / "bad.html"
    with pytest.raises(DocumentLoadError):
        LocalHtmlSource().load(path, "https://www.skatteetaten.no/")
    path.write_bytes(b"\xff")
    with pytest.raises(DocumentLoadError):
        LocalHtmlSource().load(path, "https://www.skatteetaten.no/")


def test_models_validate_timestamp_hash_and_source(raw):
    for update in [
        {"retrieved_at": datetime(2026, 1, 1)},
        {"content_hash": "bad"},
        {"source_url": "relative"},
        {"source_domain": "wrong.test"},
    ]:
        with pytest.raises(ValidationError):
            RawDocument.model_validate(raw.model_dump() | update)


def test_injected_clock_and_unicode_content(tmp_path):
    path = tmp_path / "page.html"
    html = "<main><p>Skatt på lønn: æøå</p></main>"
    path.write_text(html, encoding="utf-8")
    captured_at = datetime(2025, 4, 3, 12, 30, tzinfo=UTC)

    document = LocalHtmlSource(clock=lambda: captured_at).load(
        path, "https://www.skatteetaten.no/en/tax/?year=2025#salary"
    )

    assert document.retrieved_at == captured_at
    assert document.content == html
    assert document.source_domain == "www.skatteetaten.no"
    assert document.source_path == "/en/tax/"


def test_changed_capture_preserves_document_id_and_changes_content_hash(tmp_path):
    path = tmp_path / "page.html"
    source = LocalHtmlSource()
    url = "https://www.skatteetaten.no/en/tax/"
    path.write_text("<main>First capture</main>", encoding="utf-8")
    first = source.load(path, url)
    path.write_text("<main>Updated capture</main>", encoding="utf-8")
    second = source.load(path, url)

    assert first.id == second.id
    assert first.content_hash != second.content_hash


@pytest.mark.parametrize(
    "url", ["relative", "ftp://example.org/page", "https://user:password@example.org/page"]
)
def test_invalid_source_url_is_wrapped(tmp_path, url):
    path = tmp_path / "page.html"
    path.write_text("<main>Content</main>", encoding="utf-8")

    with pytest.raises(DocumentLoadError) as caught:
        LocalHtmlSource().load(path, url)

    assert isinstance(caught.value.__cause__, ValueError)


def test_naive_injected_clock_is_wrapped(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("<main>Content</main>", encoding="utf-8")

    with pytest.raises(DocumentLoadError) as caught:
        LocalHtmlSource(clock=lambda: datetime(2026, 1, 1)).load(path, "https://example.org/")

    assert isinstance(caught.value.__cause__, ValidationError)


def test_file_permission_error_preserves_cause(tmp_path, monkeypatch):
    failure = PermissionError("Read denied")

    def fail_read(self):
        raise failure

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(DocumentLoadError, match="Read denied") as caught:
        LocalHtmlSource().load(tmp_path / "page.html", "https://example.org/")

    assert caught.value.__cause__ is failure
