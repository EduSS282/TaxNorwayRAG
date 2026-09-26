"""Bounded read-only readiness checks; no inference or weight downloads."""

from collections.abc import Callable

import httpx

from taxguide.runtime.models import Connections, ServiceName, ServiceStatus

Probe = Callable[[ServiceName, Connections], ServiceStatus]


def probe(service: ServiceName, connections: Connections) -> ServiceStatus:
    return check(service, connections)


def check(
    service: ServiceName, connections: Connections, *, transport: httpx.BaseTransport | None = None
) -> ServiceStatus:
    url = connections.url(service)
    if (service == "embeddings" and connections.embedding_provider == "local") or (
        service == "reranker" and connections.reranker_provider == "local"
    ):
        return ServiceStatus(
            service=service,
            url=url,
            state="in_process",
            detail="In-process provider; model loads on use, readiness not tested",
        )
    try:
        with httpx.Client(
            timeout=3, follow_redirects=False, trust_env=False, transport=transport
        ) as client:
            if service == "generator":
                response = client.get(f"{url}/v1/models")
                response.raise_for_status()
                models = response.json()["data"]
                ready = any(item.get("id") == connections.generator_model for item in models)
                detail = (
                    "Model advertised; generation not tested"
                    if ready
                    else "Configured model not advertised"
                )
            elif service == "embeddings":
                response = client.get(f"{url}/api/tags")
                response.raise_for_status()
                names = {item["name"] for item in response.json()["models"]}
                model = connections.embedding_model
                ready = model in names or (":" not in model and f"{model}:latest" in names)
                detail = (
                    "Model installed; not loaded by this check"
                    if ready
                    else "Model not installed; download it outside the app"
                )
            elif service == "qdrant":
                response = client.get(f"{url}/collections/{connections.qdrant_collection}")
                response.raise_for_status()
                info = response.json()["result"]
                ready = info.get("status") == "green" and (info.get("points_count") or 0) > 0
                detail = (
                    "Collection has points; embedding compatibility not tested"
                    if ready
                    else "Collection empty or not green; index it before querying"
                )
            else:
                response = client.get(f"{url}/health")
                response.raise_for_status()
                ready = response.json().get("status") == "ok"
                detail = "Health endpoint ready; reranking not tested"
        return ServiceStatus(
            service=service,
            url=url,
            state="available" if ready else "unavailable",
            ready=ready,
            detail=detail,
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return ServiceStatus(
            service=service,
            url=url,
            state="unavailable",
            detail="Endpoint, model or collection unavailable; check service configuration",
        )
