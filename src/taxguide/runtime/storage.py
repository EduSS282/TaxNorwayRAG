"""Atomic settings snapshots and a single-controller process lock."""

import os
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from taxguide.runtime.models import SavedConnections


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock_file: BinaryIO | None = None

    def read(self) -> SavedConnections | None:
        if not self.path.exists():
            return None
        return SavedConnections.model_validate_json(self.path.read_text(encoding="utf-8"))

    def write(self, value: SavedConnections) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".connections-",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(value.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.with_suffix(".lock").open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeError("Runtime management requires exactly one API worker") from None
        self._lock_file = handle

    def release(self) -> None:
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None
