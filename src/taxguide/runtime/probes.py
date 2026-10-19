"""Bounded read-only readiness checks; no inference or weight downloads."""

from collections.abc import Callable

import httpx

from taxguide.generation.openai_compatible import GenerationError
from taxguide.generation.vertex import ADCTokenSource
from taxguide.runtime.models import Connections, ServiceName, ServiceStatus

Probe = Callable[[ServiceName, Connections], ServiceStatus]


def probe(service: ServiceName, connections: Connections) -> ServiceStatus:
    return check(service, connections)


def check(
    service: ServiceName, connections: Connections, *, transport: httpx.BaseTransport | None = None
) -> ServiceStatus:
    url = connections.url(service)
    if service == "generator" and connections.generator_provider == "vertex_ai":
        try:
            access = ADCTokenSource(timeout=3)()
            ready = bool(connections.vertex_project or access.project)
            detail = "ADC available; model access, region, quota and generation not tested"
        except GenerationError:
            ready = False
            detail = "Vertex AI ADC unavailable; configure credentials on the API host"
        return ServiceStatus(
            service=service,
            url=url,
            state="available" if ready else "unavailable",
            ready=ready,
            detail=detail,
        )
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
                if models is None:  # Ollama advertises null while no models are installed.
                    models = []
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
                    else "Ollama reachable; model missing. Wait for deployment bootstrap."
                )
            elif service == "qdrant":
                response = client.get(f"{url}/collections")
                response.raise_for_status()
                collections = response.json()["result"]["collections"]
                if not any(item["name"] == connections.qdrant_collection for item in collections):
                    return ServiceStatus(
                        service=service,
                        url=url,
                        state="needs_setup",
                        ready=False,
                        detail=(
                            "Qdrant reachable; collection missing. "
                            "Build and index from Corpus / Crawler."
                        ),
                    )
                response = client.get(f"{url}/collections/{connections.qdrant_collection}")
                response.raise_for_status()
                info = response.json()["result"]
                ready = info.get("status") == "green" and (info.get("points_count") or 0) > 0
                detail = (
                    "Collection has points; embedding compatibility not tested"
                    if ready
                    else "Qdrant reachable; collection empty or not green. Index before querying."
                )
            else:
                response = client.get(f"{url}/health")
                response.raise_for_status()
                ready = response.json().get("status") == "ok"
                detail = "Health endpoint ready; reranking not tested"
        return ServiceStatus(
            service=service,
            url=url,
            state="available"
            if ready
            else (
                "needs_setup" if service in {"qdrant", "embeddings", "generator"} else "unavailable"
            ),
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
