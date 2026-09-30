from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectConfig(ConfigModel):
    name: str = Field(default="taxguide-norway", min_length=1)
    environment: str = Field(default="development", min_length=1)


class PathConfig(ConfigModel):
    raw_data: Path = Path("data/raw")
    parsed_data: Path = Path("data/parsed")
    normalized_data: Path = Path("data/normalized")


class IngestionConfig(ConfigModel):
    parser: Literal["skatteetaten"] = "skatteetaten"
    preserve_links: bool = True
    preserve_headings: bool = True


class LoggingConfig(ConfigModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class CrawlerConfig(ConfigModel):
    user_agent: str = Field(default="TaxGuideNorwayCrawler/0.1", min_length=1)
    connect_timeout: float = Field(default=10.0, gt=0)
    read_timeout: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    request_delay: float = Field(default=0.75, ge=0)
    max_retry_after_seconds: float = Field(default=60.0, ge=0)
    max_response_bytes: int = Field(default=5_000_000, gt=0)
    max_pages: int = Field(default=50, ge=1)
    max_depth: int = Field(default=2, ge=0)
    allowed_hosts: tuple[str, ...] = ("www.skatteetaten.no", "skatteetaten.no")
    allowed_path_prefixes: tuple[str, ...] = ()


class CorpusConfig(ConfigModel):
    crawl_manifest_directory: Path = Path("data/manifests/crawl")
    raw_directory: Path = Path("data/raw/skatteetaten")
    report_directory: Path = Path("data/manifests/corpus")
    chunk_strategy: Literal["fixed", "recursive", "structural"] = "structural"
    max_tokens: int = Field(default=512, ge=1)
    overlap_tokens: int = Field(default=0, ge=0)
    embedding_provider: Literal["ollama", "local"] = "ollama"
    embedding_model: str = Field(default="qwen3-embedding:0.6b", min_length=1)
    embedding_base_url: str = Field(default="http://localhost:11434", min_length=1)
    embedding_timeout: float = Field(default=120.0, gt=0)
    embedding_batch_size: int = Field(default=32, ge=1)
    qdrant_url: str = Field(default="http://localhost:6333", min_length=1)
    qdrant_collection: str = Field(default="taxguide_chunks_ollama_qwen3_06b", min_length=1)


class RetrievalConfig(ConfigModel):
    default_mode: Literal["dense", "sparse", "hybrid", "reranked"] = "dense"
    candidate_limit: int = Field(default=10, ge=1)
    reranker_provider: Literal["local", "http", "llamacpp"] = "local"
    reranker_model: str = Field(default="Qwen/Qwen3-Reranker-0.6B", min_length=1)
    reranker_base_url: str = Field(default="http://localhost:8001", min_length=1)
    reranker_timeout: float = Field(default=120.0, gt=0)


class GenerationConfig(ConfigModel):
    """Configuration for the constrained local generation profile."""

    model_profile: Literal["portable", "balanced", "quality"] = "portable"
    provider: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = Field(default="http://127.0.0.1:8080", min_length=1)
    model: str = Field(default="Qwen/Qwen3-4B-Instruct-2507", min_length=1)
    timeout: float = Field(default=180.0, gt=0)
    evidence_max_tokens: int = Field(default=2400, ge=1)
    max_chunks_per_document: int = Field(default=2, ge=1)
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=1000, ge=1)
    structured_output: bool = True


class AppConfig(ConfigModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    crawler: CrawlerConfig = Field(default_factory=CrawlerConfig)
    corpus: CorpusConfig = Field(default_factory=CorpusConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
