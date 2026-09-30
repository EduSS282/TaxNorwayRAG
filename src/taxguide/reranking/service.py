"""Standalone FastAPI service for hosting the local Qwen reranker remotely."""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from math import isfinite
from typing import Annotated, Protocol, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from taxguide.reranking.qwen import DEFAULT_QWEN_RERANKER_MODEL_ID, _load_cross_encoder


class CrossEncoderModel(Protocol):
    def predict(
        self, sentences: list[tuple[str, str]], *, show_progress_bar: bool
    ) -> Sequence[float]: ...


DocumentText = Annotated[str, Field(min_length=1)]


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    documents: list[DocumentText] = Field(min_length=1)


class RerankResponse(BaseModel):
    scores: list[float]


class RerankerService:
    """Own one CrossEncoder instance for the lifetime of the service process."""

    def __init__(
        self,
        model_id: str,
        *,
        model_factory: Callable[[str], CrossEncoderModel] = _load_cross_encoder,
    ) -> None:
        self._model_id = model_id
        self._model_factory = model_factory
        self._model: CrossEncoderModel | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self) -> None:
        self._model_instance()

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        scores = [
            float(score)
            for score in self._model_instance().predict(
                [(query, document) for document in documents], show_progress_bar=False
            )
        ]
        if len(scores) != len(documents):
            raise ValueError("reranker returned a different number of scores than documents")
        if not all(isfinite(score) for score in scores):
            raise ValueError("reranker returned a non-finite score")
        return scores

    def _model_instance(self) -> CrossEncoderModel:
        if self._model is None:
            self._model = self._model_factory(self._model_id)
        return self._model


def create_app(
    model_id: str = DEFAULT_QWEN_RERANKER_MODEL_ID,
    *,
    model_factory: Callable[[str], CrossEncoderModel] = _load_cross_encoder,
) -> FastAPI:
    """Create the service application; model loading happens at application startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service = RerankerService(model_id, model_factory=model_factory)
        service.load()
        app.state.reranker = service
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="taxguide-reranker")
        app.state.reranker_executor = executor
        try:
            yield
        finally:
            executor.shutdown(wait=True)

    app = FastAPI(title="TaxGuide Reranker", lifespan=lifespan)

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        service = cast(RerankerService, request.app.state.reranker)
        return {"status": "ok", "model": service.model_id}

    @app.post("/rerank", response_model=RerankResponse)
    async def rerank(payload: RerankRequest, request: Request) -> RerankResponse:
        service = cast(RerankerService, request.app.state.reranker)
        executor = cast(ThreadPoolExecutor, request.app.state.reranker_executor)
        try:
            scores = await asyncio.get_running_loop().run_in_executor(
                executor, service.rerank, payload.query, payload.documents
            )
        except ValueError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return RerankResponse(scores=scores)

    return app


app = create_app()
