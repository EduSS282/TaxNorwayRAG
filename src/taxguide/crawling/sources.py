"""Named, validated crawl scope from the source-policy manifest."""

from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from taxguide.crawling.urls import validate_target
from taxguide.domain.exceptions import DisallowedDomainError, InvalidConfigurationError


class SourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    seed_url: str = Field(min_length=1)
    language: tuple[str, ...] = ()
    priority: int = Field(default=100, ge=0)
    allowed_paths: tuple[str, ...] = Field(min_length=1)

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        domain = self.domain.lower()
        return (domain,) if domain.startswith("www.") else (domain, f"www.{domain}")

    @model_validator(mode="after")
    def validate_scope(self) -> "SourceDefinition":
        if (
            self.domain != self.domain.lower()
            or urlsplit(f"https://{self.domain}").hostname != self.domain
        ):
            raise ValueError("domain must be a lowercase hostname")
        if any(
            not path.startswith("/") or "?" in path or "#" in path for path in self.allowed_paths
        ):
            raise ValueError("allowed_paths must contain absolute URL paths")
        if len(set(self.language)) != len(self.language):
            raise ValueError("language entries must be unique")
        try:
            validate_target(self.seed_url, self.allowed_hosts, self.allowed_paths)
        except (ValueError, DisallowedDomainError) as exc:
            raise ValueError(f"seed_url is outside source scope: {exc}") from exc
        return self


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sources: tuple[SourceDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "SourceManifest":
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be unique")
        return self

    def get(self, source_id: str) -> SourceDefinition:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise InvalidConfigurationError(f"Unknown source ID: {source_id}")


def load_source_manifest(path: Path) -> SourceManifest:
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
        return SourceManifest.model_validate(values)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as exc:
        raise InvalidConfigurationError(f"Invalid source manifest {path}: {exc}") from exc
