from pathlib import Path

import yaml


def test_compose_file_defines_a_persistent_local_qdrant_service() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text())

    qdrant = compose["services"]["qdrant"]
    assert qdrant["image"].startswith("qdrant/qdrant:")
    assert "6333:6333" in qdrant["ports"]
    assert "./data/qdrant:/qdrant/storage" in qdrant["volumes"]
