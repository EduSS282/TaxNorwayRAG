"""Check that the pull-only demo retains the standalone deployment contract."""

from pathlib import Path

import yaml

from taxguide.config.loader import load_config


def test_demo_uses_published_images_and_retains_private_services_and_persistence():
    source = yaml.safe_load(Path("compose.single-host.yaml").read_text(encoding="utf-8"))
    demo = yaml.safe_load(Path("compose.demo.yaml").read_text(encoding="utf-8"))
    assert demo["name"] == source["name"]  # Updates reuse the existing host's volumes.
    assert demo["volumes"] == source["volumes"]
    for name, service in demo["services"].items():
        assert "build" not in service
        original = source["services"][name].copy()
        if name in {"api", "frontend", "reranker"}:
            original.pop("build")
            assert "${TAXGUIDE_IMAGE_NAMESPACE:?" in service["image"]
            assert "${TAXGUIDE_IMAGE_TAG:?" in service["image"]
            assert f"/taxguide-{name}:" in service["image"]
            assert service["platform"] == "linux/amd64"
            actual = {
                key: value for key, value in service.items() if key not in {"image", "platform"}
            }
            if name == "api":
                original["volumes"].remove("./configs:/app/configs:ro")
            assert actual == original
        else:
            assert service == original


def test_api_image_contains_the_config_and_source_catalog_needed_without_a_checkout():
    dockerfile = Path("Dockerfile.api").read_text(encoding="utf-8")
    assert (
        "COPY configs/base.yaml configs/single-host.yaml configs/sources.yaml ./configs/"
        in dockerfile
    )
    config = load_config(Path("configs/base.yaml"), Path("configs/single-host.yaml"))
    assert config.generation.base_url == "http://ollama:11434"
    assert yaml.safe_load(Path("configs/sources.yaml").read_text(encoding="utf-8"))["sources"]
    for filename in (".dockerignore", "frontend/.dockerignore"):
        ignored = Path(filename).read_text(encoding="utf-8").splitlines()
        assert ".env" in ignored
        assert ".env.*" in ignored


def test_publication_is_gated_on_checks_and_bundle_requires_all_images():
    # BaseLoader preserves the GitHub Actions `on` key (YAML 1.1 otherwise treats it as a bool).
    workflow = yaml.load(Path(".github/workflows/ci.yaml").read_text(), Loader=yaml.BaseLoader)
    jobs = workflow["jobs"]
    publish = jobs["publish"]
    assert publish["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert set(publish["needs"]) == {"quality", "frontend", "deployment"}
    assert jobs["demo-bundle"]["needs"] == "publish"
    assert {row["name"] for row in publish["strategy"]["matrix"]["include"]} == {
        "api",
        "frontend",
        "reranker",
    }
    build = next(
        step for step in publish["steps"] if step.get("uses") == "docker/build-push-action@v6"
    )
    assert build["with"]["platforms"] == "linux/amd64"
    assert build["with"]["tags"].endswith(":sha-${{ github.sha }}")
