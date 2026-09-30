from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit


def hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def canonical_source_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username is not None:
        raise ValueError("Expected an absolute HTTP(S) source URL without credentials")
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and (parts.scheme, port) not in {("http", 80), ("https", 443)}:
        host += f":{port}"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))


def document_id_from_url(url: str) -> str:
    return hash_text(canonical_source_url(url))


def version_id_from_document(document_id: str, content_hash: str) -> str:
    """Return the stable identity of one content version of a document."""
    return hash_text(f"{document_id}:{content_hash}")
