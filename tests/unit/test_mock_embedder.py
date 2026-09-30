import pytest

from taxguide.embeddings.mock import MockEmbedder


def test_mock_embedder_is_deterministic_and_uses_the_requested_dimension() -> None:
    embedder = MockEmbedder(dimension=3)

    assert embedder.embed_query("tax return") == embedder.embed_query("tax return")
    assert len(embedder.embed_query("tax return")) == 3
    assert embedder.embed_documents(["one", "two"]) == [
        embedder.embed_query("one"),
        embedder.embed_query("two"),
    ]


def test_mock_embedder_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="positive"):
        MockEmbedder(dimension=0)
