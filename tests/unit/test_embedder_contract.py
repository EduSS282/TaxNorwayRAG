from taxguide.embeddings.base import Embedder, Embedding


def test_embedder_contract_allows_independent_adapters() -> None:
    class CharacterEmbedder:
        model_id = "character-test"
        dimension = 2

        def embed_documents(self, texts: list[str]) -> list[Embedding]:
            return [(float(len(text)), 0.0) for text in texts]

        def embed_query(self, query: str) -> Embedding:
            return (float(len(query)), 0.0)

    embedder: Embedder = CharacterEmbedder()
    assert embedder.embed_documents(["tax", "return"]) == [(3.0, 0.0), (6.0, 0.0)]
    assert embedder.embed_query("tax") == (3.0, 0.0)
