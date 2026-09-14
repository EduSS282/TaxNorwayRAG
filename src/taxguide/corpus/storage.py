import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from taxguide.corpus.models import CorpusBuildReport, CrawlManifest
from taxguide.domain.exceptions import CorpusError


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
        raise CorpusError(f"Cannot persist corpus artifact {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class FileCrawlManifestRepository:
    def __init__(self, directory: Path = Path("data/manifests/crawl")) -> None:
        self.directory = directory

    def load_all(self) -> list[CrawlManifest]:
        manifests: list[CrawlManifest] = []
        try:
            paths = sorted(self.directory.glob("*.json"))
            for path in paths:
                manifests.append(CrawlManifest.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, ValidationError) as exc:
            raise CorpusError(f"Cannot read crawl manifest in {self.directory}: {exc}") from exc
        return manifests


class FileCorpusReportRepository:
    def __init__(self, directory: Path = Path("data/manifests/corpus")) -> None:
        self.directory = directory

    def save(self, report: CorpusBuildReport) -> Path:
        path = self.directory / f"{report.run_id}.json"
        _atomic_write(
            path,
            (report.model_dump_json(indent=2) + "\n").encode("utf-8"),
        )
        return path
