"""Public HTTP request and response contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taxguide.domain.models import Chunk
from taxguide.retrieval.factory import RetrievalMode
from taxguide.vectorstores.base import ScoredChunk

Question = Annotated[str, Field(min_length=1, max_length=4000)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrieveRequest(ApiModel):
    query: Question
    mode: RetrievalMode | Literal["all"] | None = None
    limit: int = Field(default=5, ge=1, le=20)
    candidate_limit: int | None = Field(default=None, ge=1, le=100)
    tax_year: int | None = Field(default=None, ge=1900, le=2100)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class RetrieveResponse(ApiModel):
    mode: RetrievalMode | Literal["all"]
    results: list[ScoredChunk] = Field(default_factory=list)
    stages: dict[str, list[ScoredChunk]] | None = None


class RerankRequest(ApiModel):
    query: Question
    chunks: list[Chunk] = Field(min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def non_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class RerankResponse(ApiModel):
    results: list[ScoredChunk]


class QueryRequest(ApiModel):
    question: Question
    mode: RetrievalMode | None = None
    retrieval_limit: int = Field(default=5, ge=1, le=20)
    candidate_limit: int | None = Field(default=None, ge=1, le=100)
    tax_year: int | None = Field(default=None, ge=1900, le=2100)

    @field_validator("question")
    @classmethod
    def non_blank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value
