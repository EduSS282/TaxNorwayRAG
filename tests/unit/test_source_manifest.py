from pathlib import Path

import pytest

from taxguide.crawling.sources import SourceManifest, load_source_manifest
from taxguide.domain.exceptions import InvalidConfigurationError


def test_configured_source_has_bounded_seed_and_named_identity() -> None:
    source = load_source_manifest(Path("configs/sources.yaml")).get("skatteetaten-tax-return-en")
    assert source.allowed_hosts == ("skatteetaten.no", "www.skatteetaten.no")
    assert source.allowed_paths == ("/en/person/taxes/tax-return/",)
    assert source.language == ("en",)


def test_source_manifest_rejects_duplicate_ids_and_out_of_scope_seeds() -> None:
    source = {
        "id": "tax-return",
        "domain": "skatteetaten.no",
        "seed_url": "https://www.skatteetaten.no/en/person/taxes/tax-return/",
        "allowed_paths": ["/en/person/taxes/tax-return/"],
    }
    with pytest.raises(ValueError, match="unique"):
        SourceManifest.model_validate({"sources": [source, source]})
    with pytest.raises(ValueError, match="outside source scope"):
        SourceManifest.model_validate(
            {"sources": [{**source, "seed_url": "https://example.com/outside"}]}
        )


def test_unknown_source_is_reported(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match="Unknown source ID"):
        load_source_manifest(Path("configs/sources.yaml")).get("missing")
