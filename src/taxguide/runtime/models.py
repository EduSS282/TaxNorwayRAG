"""Narrow editable connections and trusted, file-only launch profiles."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from taxguide.config.models import AppConfig, ConfigModel

ServiceName = Literal["generator", "embeddings", "reranker", "qdrant"]
SERVICES: tuple[ServiceName, ...] = ("qdrant", "embeddings", "reranker", "generator")


def endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP(S) origin without credentials, path, query or fragment")
    _ = parsed.port  # Reject malformed ports.
    return value.rstrip("/")


class Connections(ConfigModel):
    generator_url: str
    generator_model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][\w./:@+-]*$")
    generator_timeout: float = Field(default=180, gt=0, le=180)
    embedding_url: str
    embedding_model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][\w./:@+-]*$")
    embedding_provider: Literal["ollama", "local"]
    reranker_url: str
    reranker_model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][\w./:@+-]*$")
    reranker_provider: Literal["llamacpp", "http", "local"]
    qdrant_url: str
    qdrant_collection: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")

    _urls = field_validator("generator_url", "embedding_url", "reranker_url", "qdrant_url")(
        endpoint
    )

    @classmethod
    def from_config(cls, config: AppConfig) -> "Connections":
        return cls(
            generator_url=config.generation.base_url,
            generator_model=config.generation.model,
            generator_timeout=config.generation.timeout,
            embedding_url=config.corpus.embedding_base_url,
            embedding_model=config.corpus.embedding_model,
            embedding_provider=config.corpus.embedding_provider,
            reranker_url=config.retrieval.reranker_base_url,
            reranker_model=config.retrieval.reranker_model,
            reranker_provider=config.retrieval.reranker_provider,
            qdrant_url=config.corpus.qdrant_url,
            qdrant_collection=config.corpus.qdrant_collection,
        )

    def apply(self, base: AppConfig) -> AppConfig:
        values = base.model_dump()
        values["generation"].update(
            base_url=self.generator_url, model=self.generator_model, timeout=self.generator_timeout
        )
        values["corpus"].update(
            embedding_base_url=self.embedding_url,
            embedding_model=self.embedding_model,
            embedding_provider=self.embedding_provider,
            qdrant_url=self.qdrant_url,
            qdrant_collection=self.qdrant_collection,
        )
        values["retrieval"].update(
            reranker_base_url=self.reranker_url,
            reranker_model=self.reranker_model,
            reranker_provider=self.reranker_provider,
        )
        return AppConfig.model_validate(values)

    def url(self, service: ServiceName) -> str:
        return {
            "generator": self.generator_url,
            "embeddings": self.embedding_url,
            "reranker": self.reranker_url,
            "qdrant": self.qdrant_url,
        }[service]


class LaunchProfile(ConfigModel):
    # Only read from an operator-owned YAML file, never accepted through HTTP.
    executable: Path
    model_path: Path | None = None
    model_id: str | None = None
    gpu_layers: int = Field(default=0, ge=0, le=200)
    context_size: int = Field(default=4096, ge=512, le=32768)
    container: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class LocalProfiles(ConfigModel):
    services: dict[ServiceName, LaunchProfile] = Field(default_factory=dict)


class ServiceStatus(ConfigModel):
    service: ServiceName
    url: str
    state: Literal[
        "available", "unavailable", "starting", "stopped", "external", "in_process", "error"
    ]
    owned: bool = False
    ready: bool = False
    can_start: bool = False
    detail: str = ""


class SavedConnections(ConfigModel):
    current: Connections
    previous: Connections | None = None
    revision: str
