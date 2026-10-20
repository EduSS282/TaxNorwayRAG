"""Verify the dedicated IAP/Vertex EU deployment without accessing GCP."""

import json
from pathlib import Path

import httpx
import yaml

from taxguide.config.loader import load_config
from taxguide.generation.factory import create_generator
from taxguide.generation.vertex import VertexAccess, VertexAIGenerator
from taxguide.runtime.models import Connections

DEPLOYMENT = Path("deployments/fieldmind-gcp")


def test_fieldmind_stack_only_publishes_iap_port_and_never_builds_or_downloads_local_generation():
    compose = yaml.safe_load((DEPLOYMENT / "compose.yaml").read_text(encoding="utf-8"))
    assert compose["name"] == "taxnorge-fieldmind"
    services = compose["services"]
    assert set(services) == {"api", "frontend", "qdrant", "ollama", "models-init", "reranker"}
    assert services["frontend"]["ports"] == ["8080:3000"]
    for name, service in services.items():
        assert "build" not in service
        assert "deploy" not in service  # This VM has no GPU.
        if name != "frontend":
            assert "ports" not in service
        assert service["logging"]["options"] == {"max-size": "10m", "max-file": "3"}
    assert services["models-init"]["command"] == ["ollama pull qwen3-embedding:0.6b"]
    assert services["frontend"]["environment"]["TAXGUIDE_API_URL"] == "http://api:8000"
    assert set(compose["volumes"]) == {"vectors", "app-data", "ollama-models", "reranker-models"}


def test_fieldmind_yaml_factory_and_runtime_agree_on_eu_origin_and_omit_unsupported_thinking(
    monkeypatch,
):
    config = load_config(Path("configs/base.yaml"), DEPLOYMENT / "vertex.yaml")
    compose = yaml.safe_load((DEPLOYMENT / "compose.yaml").read_text(encoding="utf-8"))
    api = compose["services"]["api"]
    assert api["environment"]["TAXGUIDE_OVERLAY"] == "/app/deployment/vertex.yaml"
    assert "./vertex.yaml:/app/deployment/vertex.yaml:ro" in api["volumes"]
    assert config.corpus.embedding_base_url == "http://ollama:11434"
    assert config.corpus.qdrant_url == "http://qdrant:6333"
    assert config.retrieval.reranker_base_url == "http://reranker:8001"
    assert config.generation.provider == "vertex_ai"
    assert config.generation.vertex_thinking_budget is None
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in api["environment"]
    assert not any("secrets" in mount for mount in api["volumes"])
    expected_origin = "https://aiplatform.eu.rep.googleapis.com"
    assert Connections.from_config(config).url("generator") == expected_origin
    assert api["environment"]["TAXGUIDE_SERVICE_ORIGINS"] == expected_origin

    def respond(request):
        assert str(request.url) == (
            expected_origin + "/v1/projects/eduardo-taxnorge/locations/eu/"
            "publishers/google/models/gemini-3.5-flash:generateContent"
        )
        generation = json.loads(request.content)["generationConfig"]
        assert "thinkingConfig" not in generation
        assert generation["maxOutputTokens"] == 4096
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]},
        )

    def injected_generator(model_id, **kwargs):
        return VertexAIGenerator(
            model_id,
            token_source=lambda: VertexAccess("test-token", "other-adc-project"),
            client=httpx.Client(transport=httpx.MockTransport(respond)),
            **kwargs,
        )

    monkeypatch.setattr("taxguide.generation.factory.VertexAIGenerator", injected_generator)
    instance = create_generator(config.generation)
    assert (
        instance.generate(
            [{"role": "user", "content": "Test"}],
            temperature=config.generation.temperature,
            max_tokens=config.generation.max_tokens,
        )
        == "{}"
    )
