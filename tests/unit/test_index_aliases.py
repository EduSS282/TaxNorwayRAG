from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import DeleteAliasOperation, Distance, RenameAliasOperation, VectorParams

from taxguide.domain.exceptions import VectorStoreError
from taxguide.indexing.aliases import QdrantIndexAliases


class FakeAliasClient:
    def __init__(self) -> None:
        self.collections = {"candidate-a", "candidate-b", "candidate-c"}
        self.aliases: dict[str, str] = {}

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def get_aliases(self) -> object:
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=alias, collection_name=collection)
                for alias, collection in self.aliases.items()
            ]
        )

    def update_collection_aliases(self, *, change_aliases_operations: list[Any]) -> bool:
        changed = self.aliases.copy()
        for operation in change_aliases_operations:
            if isinstance(operation, DeleteAliasOperation):
                changed.pop(operation.delete_alias.alias_name, None)
            elif isinstance(operation, RenameAliasOperation):
                target = changed.pop(operation.rename_alias.old_alias_name)
                changed[operation.rename_alias.new_alias_name] = target
            else:
                alias = operation.create_alias.alias_name
                if alias in changed:
                    raise ValueError(f"alias already exists: {alias}")
                changed[alias] = operation.create_alias.collection_name
        self.aliases = changed
        return True


def test_promote_keeps_previous_collection_and_rollback_swaps_aliases() -> None:
    client = FakeAliasClient()
    aliases = QdrantIndexAliases(client)

    assert aliases.promote(candidate="candidate-a") is None
    assert client.aliases == {"taxguide_current": "candidate-a"}
    assert aliases.promote(candidate="candidate-b") == "candidate-a"
    assert client.aliases == {
        "taxguide_current": "candidate-b",
        "taxguide_previous": "candidate-a",
    }
    assert aliases.rollback() == ("candidate-a", "candidate-b")
    assert client.aliases == {
        "taxguide_current": "candidate-a",
        "taxguide_previous": "candidate-b",
    }


def test_first_promote_adopts_configured_physical_collection_for_rollback() -> None:
    client = FakeAliasClient()
    client.collections.add("production")
    aliases = QdrantIndexAliases(client)

    assert aliases.promote(candidate="candidate-a", initial_collection="production") == "production"
    assert client.aliases == {
        "taxguide_current": "candidate-a",
        "taxguide_previous": "production",
    }
    assert aliases.rollback() == ("production", "candidate-a")


def test_initial_collection_is_ignored_after_current_alias_exists() -> None:
    client = FakeAliasClient()
    aliases = QdrantIndexAliases(client)
    aliases.promote(candidate="candidate-a")

    assert aliases.promote(candidate="candidate-b", initial_collection="missing") == "candidate-a"


def test_promote_rejects_orphaned_previous_alias() -> None:
    client = FakeAliasClient()
    client.aliases["taxguide_previous"] = "candidate-a"
    with pytest.raises(VectorStoreError, match="without an active alias"):
        QdrantIndexAliases(client).promote(candidate="candidate-b")


def test_first_promotion_and_rollback_work_with_qdrant_client() -> None:
    client = QdrantClient(":memory:")
    for name in ("production", "candidate"):
        client.create_collection(
            collection_name=name, vectors_config=VectorParams(size=2, distance=Distance.COSINE)
        )
    aliases = QdrantIndexAliases(client)

    assert aliases.promote(candidate="candidate", initial_collection="production") == "production"
    assert aliases.rollback() == ("production", "candidate")


def test_promote_replaces_old_rollback_alias_atomically() -> None:
    client = FakeAliasClient()
    aliases = QdrantIndexAliases(client)
    aliases.promote(candidate="candidate-a")
    aliases.promote(candidate="candidate-b")

    aliases.promote(candidate="candidate-c")

    assert client.aliases == {
        "taxguide_current": "candidate-c",
        "taxguide_previous": "candidate-b",
    }


def test_alias_operations_reject_missing_candidates_and_rollback_targets() -> None:
    client = FakeAliasClient()
    aliases = QdrantIndexAliases(client)

    with pytest.raises(VectorStoreError, match="does not exist"):
        aliases.promote(candidate="missing")
    with pytest.raises(VectorStoreError, match="must exist for rollback"):
        aliases.rollback()


def test_alias_names_must_be_distinct() -> None:
    with pytest.raises(ValueError, match="must differ"):
        QdrantIndexAliases(FakeAliasClient()).promote(
            candidate="candidate-a", alias="same", previous_alias="same"
        )
