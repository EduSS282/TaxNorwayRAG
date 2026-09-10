import json
import os
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
