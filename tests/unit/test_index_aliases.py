from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client.models import DeleteAliasOperation, RenameAliasOperation

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
