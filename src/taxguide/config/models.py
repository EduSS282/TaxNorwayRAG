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
    max_response_bytes: int = Field(default=5_000_000, gt=0)
    max_pages: int = Field(default=50, ge=1)
    max_depth: int = Field(default=2, ge=0)
    allowed_hosts: tuple[str, ...] = ("www.skatteetaten.no", "skatteetaten.no")
    allowed_path_prefixes: tuple[str, ...] = ()


class AppConfig(ConfigModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    crawler: CrawlerConfig = Field(default_factory=CrawlerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
