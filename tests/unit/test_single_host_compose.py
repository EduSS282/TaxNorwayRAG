"""Check deployment wiring and persistence without downloading real model weights."""

from pathlib import Path

import yaml

from taxguide.config.loader import load_config


def test_standalone_stack_wires_all_dependencies_without_publishing_internal_services():
    compose = yaml.safe_load(Path("compose.single-host.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert set(services) == {"api", "frontend", "qdrant", "ollama", "models-init", "reranker"}
    for name in set(services) - {"frontend"}:
        assert "ports" not in services[name]
    assert services["frontend"]["ports"] == ["127.0.0.1:${TAXGUIDE_UI_PORT:-3000}:3000"]
    assert services["frontend"]["environment"]["TAXGUIDE_API_URL"] == "http://api:8000"
    assert services["api"]["depends_on"]["qdrant"]["condition"] == "service_healthy"
    assert "models-init" not in services["api"]["depends_on"]  # UI stays available during download.
    assert "?Set a random" in services["api"]["environment"]["TAXGUIDE_ADMIN_TOKEN"]
    assert "./secrets:/run/secrets:ro" in services["api"]["volumes"]
    assert set(compose["volumes"]) == {"vectors", "app-data", "ollama-models", "reranker-models"}
    assert "secrets/" in Path(".gitignore").read_text()
    assert "secrets" in Path(".dockerignore").read_text()


def test_single_host_models_match_bootstrap_and_pinned_runtime_config():
    compose = yaml.safe_load(Path("compose.single-host.yaml").read_text(encoding="utf-8"))
    config = load_config(Path("configs/base.yaml"), Path("configs/single-host.yaml"))
    services = compose["services"]
    command = services["models-init"]["command"][0]
    assert f"ollama pull {config.corpus.embedding_model}" in command
    assert f"ollama pull {config.generation.model}" in command
    assert config.corpus.embedding_base_url == config.generation.base_url == "http://ollama:11434"
    assert config.corpus.qdrant_url == "http://qdrant:6333"
    assert config.retrieval.reranker_base_url == "http://reranker:8001"
    assert config.retrieval.reranker_provider == "http"
    assert services["ollama"]["image"] == services["models-init"]["image"]
    assert ":latest" not in services["ollama"]["image"]
    assert "--extra cpu-models --no-cache" in Path("Dockerfile.reranker").read_text()
    assert "COMPOSE_FILE=compose.single-host.yaml" in Path(".env.single-host.example").read_text()
