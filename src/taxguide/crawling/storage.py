import json
import os
import re
import tempfile
from pathlib import Path

from taxguide.crawling.models import CrawledPage
from taxguide.domain.exceptions import CrawlerError


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError as exc:
        raise CrawlerError(f"Cannot persist crawl artifact {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class FileCrawlArtifactRepository:
    def __init__(self, output_directory: Path = Path("data")) -> None:
        self.raw_directory = output_directory / "raw" / "skatteetaten"
        self.manifest_directory = output_directory / "manifests" / "crawl"

    def save(self, page: CrawledPage) -> None:
        raw_path = self.raw_directory / f"{page.document_id}.html"
        manifest_path = self.manifest_directory / f"{page.document_id}.json"
        _atomic_write(raw_path, page.raw_html.encode("utf-8"))
        manifest = page.model_dump(mode="json", exclude={"raw_html"})
        manifest["wizard_ids"] = page.wizard.wizard_ids if page.wizard else []
        _atomic_write(
            manifest_path,
            (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        )

    def content_hash_for(self, document_id: str) -> str | None:
        """Return the latest stored capture hash, or None for a first capture."""
        manifest_path = self.manifest_directory / f"{document_id}.json"
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CrawlerError(
                f"Cannot read previous crawl manifest {manifest_path}: {exc}"
            ) from exc
        content_hash = value.get("content_sha256") if isinstance(value, dict) else None
        if not isinstance(content_hash, str) or re.fullmatch(r"[a-f0-9]{64}", content_hash) is None:
            raise CrawlerError(f"Previous crawl manifest has no content hash: {manifest_path}")
        return content_hash
