from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from taxguide.domain.enums import TaxTopic
from taxguide.domain.exceptions import VectorStoreError
from taxguide.domain.models import Chunk, ChunkMetadata
from taxguide.retrieval.filters import RetrievalFilter
from taxguide.vectorstores.qdrant import QdrantVectorStore, qdrant_point_id


class FakeQdrantClient:
    def __init__(self) -> None:
        self.points: list[dict[str, Any]] = []
        self.upsert_calls: list[list[dict[str, Any]]] = []
        self.collection_present = True
        self.vector_size = 2
        self.distance = "Cosine"
        self.created_vectors_config: Any | None = None

    def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "taxguide_chunks"
        return self.collection_present

    def create_collection(self, *, collection_name: str, vectors_config: Any) -> bool:
        assert collection_name == "taxguide_chunks"
        self.collection_present = True
        self.vector_size = vectors_config.size
        self.distance = vectors_config.distance.value
        self.created_vectors_config = vectors_config
        return True

    def get_collection(self, collection_name: str) -> object:
        assert collection_name == "taxguide_chunks"
        vectors = SimpleNamespace(
            size=self.vector_size,
            distance=SimpleNamespace(value=self.distance),
        )
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))

    def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> None:
        assert collection_name == "taxguide_chunks"
        self.points = points
        self.upsert_calls.append(points)

    def query_points(
        self, *, collection_name: str, query: list[float], limit: int, with_payload: bool
    ) -> "FakeQueryResponse":
        assert collection_name == "taxguide_chunks"
        assert query == [0.1, 0.2]
        assert limit == 1
        assert with_payload is True
        return FakeQueryResponse([FakeScoredPoint(self.points[0]["payload"], 0.9)])


class FakeScoredPoint:
    def __init__(self, payload: dict[str, Any], score: float) -> None:
        self.payload = payload
        self.score = score


class FakeQueryResponse:
    def __init__(self, points: list[FakeScoredPoint]) -> None:
        self.points = points


def test_qdrant_store_indexes_chunk_payloads_and_restores_search_results() -> None:
    client = FakeQdrantClient()
    store = QdrantVectorStore(client)
    chunk = _chunk()

    store.upsert([chunk], [(0.1, 0.2)])

    assert client.points[0]["id"] == qdrant_point_id(chunk.id)
    assert client.points[0]["payload"]["chunk_id"] == chunk.id
    assert client.points[0]["payload"]["text"] == chunk.text
    assert client.points[0]["payload"]["metadata"]["topic"] == "deadlines"
    result = store.search((0.1, 0.2), limit=1)[0]
    assert result.chunk == chunk
    assert result.score == 0.9


def test_qdrant_store_rejects_invalid_upsert_and_search_arguments() -> None:
    store = QdrantVectorStore(FakeQdrantClient())

    with pytest.raises(ValueError, match="same length"):
        store.upsert([_chunk()], [])
    with pytest.raises(ValueError, match="positive"):
        store.search((0.1, 0.2), limit=0)


def test_qdrant_store_creates_a_missing_cosine_collection() -> None:
    client = FakeQdrantClient()
    client.collection_present = False

    QdrantVectorStore(client).ensure_collection(1024)

    assert client.created_vectors_config is not None
    assert client.vector_size == 1024
    assert client.distance == "Cosine"


@pytest.mark.parametrize(
    ("vector_size", "distance", "message"),
    [(3, "Cosine", "vector size 3"), (2, "Dot", "expected 'Cosine'")],
)
def test_qdrant_store_rejects_an_incompatible_collection(
    vector_size: int, distance: str, message: str
) -> None:
    client = FakeQdrantClient()
    client.vector_size = vector_size
    client.distance = distance

    with pytest.raises(VectorStoreError, match=message):
        QdrantVectorStore(client).validate_collection(2)


def test_qdrant_store_rejects_named_vector_collections() -> None:
    class NamedVectorClient(FakeQdrantClient):
        def get_collection(self, collection_name: str) -> object:
            return SimpleNamespace(
                config=SimpleNamespace(params=SimpleNamespace(vectors={"dense": object()}))
            )

    with pytest.raises(VectorStoreError, match="named-vector"):
        QdrantVectorStore(NamedVectorClient()).validate_collection(2)


@pytest.mark.parametrize("vector_size", [0, -1])
def test_qdrant_store_rejects_invalid_collection_vector_size(vector_size: int) -> None:
    store = QdrantVectorStore(FakeQdrantClient())

    with pytest.raises(ValueError, match="vector_size"):
        store.ensure_collection(vector_size)
    with pytest.raises(ValueError, match="vector_size"):
        store.validate_collection(vector_size)


def test_qdrant_store_translates_tax_year_to_a_payload_filter() -> None:
    class FilterClient(FakeQdrantClient):
        def query_points(self, **kwargs: Any) -> "FakeQueryResponse":
            self.query_filter = kwargs["query_filter"]
            return FakeQueryResponse([])

    client = FilterClient()
    QdrantVectorStore(client).search((0.1, 0.2), limit=1, filters=RetrievalFilter(tax_year=2025))

    condition = client.query_filter.must[0]
    assert condition.key == "metadata.tax_year"
    assert condition.match.value == 2025


def test_qdrant_store_translates_every_declared_metadata_filter() -> None:
    class FilterClient(FakeQdrantClient):
        def query_points(self, **kwargs: Any) -> "FakeQueryResponse":
            self.query_filter = kwargs["query_filter"]
            return FakeQueryResponse([])

    client = FilterClient()
    QdrantVectorStore(client).search(
        (0.1, 0.2),
        limit=1,
        filters=RetrievalFilter(
            tax_year=2025,
            topic=TaxTopic.DEADLINES,
            language="en",
            source="www.skatteetaten.no",
            document_type="guidance",
            audience="individual",
        ),
    )

    values = {condition.key: condition.match.value for condition in client.query_filter.must}
    assert values == {
        "metadata.tax_year": 2025,
        "metadata.topic": "deadlines",
        "metadata.language": "en",
        "metadata.source_domain": "www.skatteetaten.no",
        "metadata.document_type": "guidance",
        "metadata.audience": "individual",
    }


def test_qdrant_store_loads_all_persisted_chunk_payloads() -> None:
    chunk = _chunk()

    class ScrollClient(FakeQdrantClient):
        def scroll(self, **_: Any) -> tuple[list[FakeScoredPoint], None]:
            point = FakeScoredPoint({**chunk.model_dump(mode="json"), "chunk_id": chunk.id}, 0)
            return [point], None

    assert QdrantVectorStore(ScrollClient()).load_chunks() == [chunk]


def test_qdrant_store_loads_payloads_from_before_document_versioning() -> None:
    chunk = _chunk()
    payload = {**chunk.model_dump(mode="json"), "chunk_id": chunk.id}
    del payload["metadata"]["version_id"]

    class ScrollClient(FakeQdrantClient):
        def scroll(self, **_: Any) -> tuple[list[FakeScoredPoint], None]:
            return [FakeScoredPoint(payload, 0)], None

    restored = QdrantVectorStore(ScrollClient()).load_chunks()[0]

    assert restored.metadata.version_id is None


def test_qdrant_point_ids_are_stable_distinct_and_valid_uuids() -> None:
    first = qdrant_point_id("a" * 64)

    assert first == qdrant_point_id("a" * 64)
    assert first != qdrant_point_id("b" * 64)
    assert str(UUID(first)) == first


def test_repeated_upserts_target_the_same_deterministic_point() -> None:
    client = FakeQdrantClient()
    store = QdrantVectorStore(client)
    chunk = _chunk()

    store.upsert([chunk], [(0.1, 0.2)])
    store.upsert([chunk], [(0.1, 0.2)])

    assert len(client.upsert_calls) == 2
    assert client.upsert_calls[0][0]["id"] == client.upsert_calls[1][0]["id"]


def test_qdrant_http_errors_include_status_and_response_body() -> None:
    class RejectedRequest(Exception):
        status_code = 400
        content = b'{"status":{"error":"invalid point id"}}'

    class RejectedClient(FakeQdrantClient):
        def upsert(self, *, collection_name: str, points: list[dict[str, Any]]) -> None:
            raise RejectedRequest("bad request")

    with pytest.raises(VectorStoreError, match="status 400: .*invalid point id"):
        QdrantVectorStore(RejectedClient()).upsert([_chunk()], [(0.1, 0.2)])


def _chunk() -> Chunk:
    return Chunk(
        id="a" * 64,
        document_id="b" * 64,
        text="Tax return deadline",
        section_path=("Return",),
        chunk_index=0,
        token_count=3,
        content_hash="c" * 64,
        metadata=ChunkMetadata(
            source_url="https://www.skatteetaten.no/en/example",
            source_domain="www.skatteetaten.no",
            topic=TaxTopic.DEADLINES,
            retrieved_at=datetime(2026, 9, 9, tzinfo=UTC),
            document_content_hash="d" * 64,
        ),
    )
