"""FastAPI boundary for independent retrieval, reranking, and grounded answers."""

from collections.abc import Awaitable, Callable
from importlib.metadata import PackageNotFoundError, version
from os import environ
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from taxguide.api.backend import ApiBackend, ConfiguredBackend
from taxguide.api.models import (
    QueryRequest,
    RerankRequest,
    RerankResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from taxguide.config.loader import load_config
from taxguide.config.models import AppConfig
from taxguide.domain.exceptions import (
    CrossYearRetrievalError,
    TaxguideError,
    TemporalResolutionError,
)
from taxguide.generation.service import GroundedRagResult, GroundedRagStatus
from taxguide.observability.request import (
    MetricsRegistry,
    RequestTrace,
    log_request,
    timed_stage,
    trace_scope,
)
from taxguide.retrieval.factory import RetrievalMode


def _settings() -> AppConfig:
    base = Path(environ.get("TAXGUIDE_CONFIG", "configs/base.yaml"))
    overlay_name = environ.get("TAXGUIDE_OVERLAY")
    overlay = Path(overlay_name) if overlay_name else None
    if base.exists() or "TAXGUIDE_CONFIG" in environ:
        return load_config(base, overlay)
    return load_config(overlay) if overlay is not None else AppConfig()


def _version() -> str:
    try:
        return version("taxguide-norway")
    except PackageNotFoundError:
        return "unknown"


_LOGGABLE_PATHS = {
    "/v1/health",
    "/v1/version",
    "/v1/metrics",
    "/v1/retrieve",
    "/v1/rerank",
    "/v1/query",
    "/openapi.json",
    "/docs",
    "/redoc",
}


def create_app(
    *,
    settings: AppConfig | None = None,
    backend: ApiBackend | None = None,
    metrics: MetricsRegistry | None = None,
    clock: Callable[[], float] = perf_counter,
) -> FastAPI:
    """Compose a testable HTTP boundary without loading models or contacting Qdrant."""
    config = settings or _settings()
    service = backend or ConfiguredBackend(config)
    registry = metrics or MetricsRegistry()
    package_version = _version()
    application = FastAPI(title="TaxGuide Norway API", version=package_version)

    @application.middleware("http")
    async def observe_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace = RequestTrace.start(registry, request.headers.get("traceparent"))
        started = clock()
        status = 500
        with trace_scope(trace):
            try:
                try:
                    response = await call_next(request)
                except Exception:
                    response = JSONResponse(
                        status_code=500, content={"detail": "internal server error"}
                    )
                status = response.status_code
                response.headers["X-Request-ID"] = trace.request_id
                response.headers["X-Trace-ID"] = trace.trace_id
                response.headers["traceparent"] = trace.traceparent
                return response
            finally:
                elapsed = clock() - started
                registry.observe("http_request", elapsed)
                log_request(
                    trace,
                    method=request.method,
                    path=request.url.path if request.url.path in _LOGGABLE_PATHS else "<other>",
                    status=status,
                    duration_seconds=elapsed,
                )

    @application.get("/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/version")
    def api_version() -> dict[str, str]:
        return {"name": "taxguide-norway", "version": package_version, "api_version": "v1"}

    @application.get("/v1/metrics")
    def latency_metrics() -> dict[str, object]:
        return {"latency_seconds": registry.snapshot()}

    @application.post("/v1/retrieve", response_model=RetrieveResponse)
    def retrieve(payload: RetrieveRequest) -> RetrieveResponse:
        mode = payload.mode or config.retrieval.default_mode
        candidate_limit = payload.candidate_limit or config.retrieval.candidate_limit
        if mode in {"reranked", "all"} and candidate_limit < payload.limit:
            raise HTTPException(422, "candidate_limit must be at least limit")
        try:
            with timed_stage("retrieval"):
                if mode == "all":
                    stages = {}
                    diagnostic_modes: tuple[tuple[str, RetrievalMode], ...] = (
                        ("dense", "dense"),
                        ("sparse", "sparse"),
                        ("fused", "hybrid"),
                        ("reranked", "reranked"),
                    )
                    for stage_name, selected_mode in diagnostic_modes:
                        with timed_stage(f"retrieval_{stage_name}"):
                            stages[stage_name] = service.retrieve(
                                payload.query,
                                mode=selected_mode,
                                limit=payload.limit,
                                candidate_limit=candidate_limit,
                                tax_year=payload.tax_year,
                            )
                    return RetrieveResponse(mode="all", stages=stages)
                results = service.retrieve(
                    payload.query,
                    mode=mode,
                    limit=payload.limit,
                    candidate_limit=candidate_limit,
                    tax_year=payload.tax_year,
                )
        except (TaxguideError, RuntimeError, ValueError) as exc:
            raise _api_error(exc) from exc
        return RetrieveResponse(mode=mode, results=results)

    @application.post("/v1/rerank", response_model=RerankResponse)
    def rerank(payload: RerankRequest) -> RerankResponse:
        try:
            with timed_stage("reranking"):
                results = service.rerank(payload.query, payload.chunks, limit=payload.limit)
        except (TaxguideError, RuntimeError, ValueError) as exc:
            raise _api_error(exc) from exc
        return RerankResponse(results=results)

    @application.post("/v1/query", response_model=GroundedRagResult)
    def query(payload: QueryRequest) -> GroundedRagResult | JSONResponse:
        mode = payload.mode or config.retrieval.default_mode
        candidate_limit = payload.candidate_limit or config.retrieval.candidate_limit
        if mode == "reranked" and candidate_limit < payload.retrieval_limit:
            raise HTTPException(422, "candidate_limit must be at least retrieval_limit")
        try:
            result = service.query(
                payload.question,
                mode=mode,
                retrieval_limit=payload.retrieval_limit,
                candidate_limit=candidate_limit,
                tax_year=payload.tax_year,
            )
        except (TaxguideError, RuntimeError, ValueError) as exc:
            raise _api_error(exc) from exc
        if result.status is GroundedRagStatus.FAILED:
            safe_result = result.model_copy(update={"error": "configured service unavailable"})
            return JSONResponse(status_code=503, content=safe_result.model_dump(mode="json"))
        return result

    return application


def _api_error(error: Exception) -> HTTPException:
    if isinstance(error, TemporalResolutionError):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, CrossYearRetrievalError):
        return HTTPException(status_code=502, detail="retriever violated tax-year scope")
    if isinstance(error, ValueError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=503, detail="configured service unavailable")


app = create_app()
