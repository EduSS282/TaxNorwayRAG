"""Low-cardinality latency metrics and request-scoped trace spans."""

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger("taxguide.api.requests")
logger.setLevel(logging.INFO)
_current_trace: ContextVar["RequestTrace | None"] = ContextVar(
    "taxguide_request_trace", default=None
)
_BUCKETS = (0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 120.0)


@dataclass
class LatencySummary:
    count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0
    buckets: dict[str, int] = field(default_factory=lambda: {str(bound): 0 for bound in _BUCKETS})

    def observe(self, seconds: float) -> None:
        self.count += 1
        self.total_seconds += seconds
        self.max_seconds = max(self.max_seconds, seconds)
        for bound in _BUCKETS:
            if seconds <= bound:
                self.buckets[str(bound)] += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "count": self.count,
            "total_seconds": self.total_seconds,
            "max_seconds": self.max_seconds,
            "buckets": dict(self.buckets),
        }


class MetricsRegistry:
    """Per-process aggregate metrics; labels are fixed stage names only."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stages: dict[str, LatencySummary] = {}

    def observe(self, stage: str, seconds: float) -> None:
        with self._lock:
            self._stages.setdefault(stage, LatencySummary()).observe(seconds)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {stage: summary.snapshot() for stage, summary in self._stages.items()}


@dataclass
class RequestTrace:
    trace_id: str
    request_id: str
    span_id: str
    parent_span_id: str | None
    metrics: MetricsRegistry
    spans: list[dict[str, object]] = field(default_factory=list)

    @classmethod
    def start(cls, metrics: MetricsRegistry, traceparent: str | None = None) -> "RequestTrace":
        match = re.fullmatch(r"00-([a-f0-9]{32})-([a-f0-9]{16})-[a-f0-9]{2}", traceparent or "")
        valid_parent = (
            match is not None and match.group(1) != "0" * 32 and match.group(2) != "0" * 16
        )
        return cls(
            trace_id=match.group(1) if valid_parent and match is not None else uuid4().hex,
            request_id=str(uuid4()),
            span_id=uuid4().hex[:16],
            parent_span_id=match.group(2) if valid_parent and match is not None else None,
            metrics=metrics,
        )

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"

    def record(self, stage: str, seconds: float) -> None:
        self.metrics.observe(stage, seconds)
        self.spans.append({"stage": stage, "duration_ms": round(seconds * 1000, 3)})


@contextmanager
def trace_scope(trace: RequestTrace) -> Iterator[None]:
    token = _current_trace.set(trace)
    try:
        yield
    finally:
        _current_trace.reset(token)


@contextmanager
def timed_stage(stage: str) -> Iterator[None]:
    trace = _current_trace.get()
    if trace is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        trace.record(stage, perf_counter() - started)


def log_request(
    trace: RequestTrace, *, method: str, path: str, status: int, duration_seconds: float
) -> None:
    """Never include request bodies, query strings, answer text, or source excerpts."""
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": trace.request_id,
                "trace_id": trace.trace_id,
                "parent_span_id": trace.parent_span_id,
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration_seconds * 1000, 3),
                "spans": trace.spans,
            },
            separators=(",", ":"),
        )
    )
