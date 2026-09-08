from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from taxguide.config.models import AppConfig
from taxguide.domain.exceptions import InvalidConfigurationError


def _read(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise InvalidConfigurationError(f"Cannot load configuration {path}: {exc}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise InvalidConfigurationError(f"Configuration {path} must be a YAML mapping")
    return value


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        previous = merged.get(key)
        merged[key] = (
            _merge(previous, value)
            if isinstance(previous, dict) and isinstance(value, dict)
            else value
        )
    return merged


def load_config(base: Path, overlay: Path | None = None) -> AppConfig:
    values = _read(base)
    if overlay is not None:
        values = _merge(values, _read(overlay))
    try:
        return AppConfig.model_validate(values)
    except ValidationError as exc:
        raise InvalidConfigurationError(f"Invalid configuration: {exc}") from exc
