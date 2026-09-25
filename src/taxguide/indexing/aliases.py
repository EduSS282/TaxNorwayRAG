"""Atomic Qdrant alias promotion and rollback."""

from collections.abc import Sequence
from typing import Any, Protocol

from taxguide.domain.exceptions import VectorStoreError


class QdrantAliasClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool: ...

    def get_aliases(self) -> Any: ...

    def update_collection_aliases(self, *, change_aliases_operations: Sequence[Any]) -> bool: ...


class QdrantIndexAliases:
    """Keep a stable read alias and one rollback alias using atomic alias updates."""

    def __init__(self, client: QdrantAliasClient) -> None:
        self._client = client

    def promote(
        self,
        *,
        candidate: str,
        alias: str = "taxguide_current",
        previous_alias: str = "taxguide_previous",
    ) -> str | None:
        """Point `alias` at a reviewed physical candidate and retain the former target."""
        self._validate_names(candidate, alias, previous_alias)
        try:
            if not self._client.collection_exists(candidate):
                raise VectorStoreError(f"Candidate collection {candidate!r} does not exist")
            aliases = self._aliases()
            current_collection = aliases.get(alias)
            previous_collection = aliases.get(previous_alias)
            if candidate in {alias, previous_alias}:
                raise VectorStoreError("Candidate collection must use a physical collection name")
            if current_collection == candidate:
                raise VectorStoreError(f"Candidate {candidate!r} is already the active index")
            if previous_collection == candidate:
                raise VectorStoreError("Candidate is already the rollback target")

            from qdrant_client.models import (
                CreateAlias,
                CreateAliasOperation,
                DeleteAlias,
                DeleteAliasOperation,
                RenameAlias,
                RenameAliasOperation,
            )

            operations: list[Any] = []
            if current_collection is not None:
                if previous_collection is not None:
                    operations.append(
                        DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=previous_alias))
                    )
                operations.append(
                    RenameAliasOperation(
                        rename_alias=RenameAlias(
                            old_alias_name=alias, new_alias_name=previous_alias
                        )
                    )
                )
            operations.append(
                CreateAliasOperation(
                    create_alias=CreateAlias(collection_name=candidate, alias_name=alias)
                )
            )
            self._client.update_collection_aliases(change_aliases_operations=operations)
            return current_collection
        except VectorStoreError:
            raise
        except Exception as exc:
            raise _alias_error(exc) from exc

    def rollback(
        self,
        *,
        alias: str = "taxguide_current",
        previous_alias: str = "taxguide_previous",
    ) -> tuple[str, str]:
        """Swap the active and rollback targets atomically, retaining both versions."""
        self._validate_names("rollback-candidate", alias, previous_alias)
        try:
            aliases = self._aliases()
            current_collection = aliases.get(alias)
            previous_collection = aliases.get(previous_alias)
            if current_collection is None or previous_collection is None:
                raise VectorStoreError(
                    f"Both aliases {alias!r} and {previous_alias!r} must exist for rollback"
                )
            if current_collection == previous_collection:
                raise VectorStoreError("Current and previous aliases point to the same collection")

            from qdrant_client.models import (
                CreateAlias,
                CreateAliasOperation,
                DeleteAlias,
                DeleteAliasOperation,
                RenameAlias,
                RenameAliasOperation,
            )

            operations = [
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)),
                RenameAliasOperation(
                    rename_alias=RenameAlias(old_alias_name=previous_alias, new_alias_name=alias)
                ),
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=current_collection,
                        alias_name=previous_alias,
                    )
                ),
            ]
            self._client.update_collection_aliases(change_aliases_operations=operations)
            return previous_collection, current_collection
        except VectorStoreError:
            raise
        except Exception as exc:
            raise _alias_error(exc) from exc

    def _aliases(self) -> dict[str, str]:
        response = self._client.get_aliases()
        try:
            return {item.alias_name: item.collection_name for item in response.aliases}
        except (AttributeError, TypeError) as exc:
            raise VectorStoreError("Qdrant returned an unreadable alias list") from exc

    @staticmethod
    def _validate_names(candidate: str, alias: str, previous_alias: str) -> None:
        if not candidate.strip() or not alias.strip() or not previous_alias.strip():
            raise ValueError("candidate and alias names must not be blank")
        if alias == previous_alias:
            raise ValueError("current and previous alias names must differ")


def _alias_error(error: Exception) -> VectorStoreError:
    return VectorStoreError(f"Qdrant alias operation failed: {error}")
