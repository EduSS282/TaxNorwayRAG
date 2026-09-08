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


class AppConfig(ConfigModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
