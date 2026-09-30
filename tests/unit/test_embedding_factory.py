from taxguide.config.models import CorpusConfig
from taxguide.embeddings.factory import create_embedder
from taxguide.embeddings.ollama import OllamaEmbedder
from taxguide.embeddings.qwen import QwenEmbedder


def test_factory_selects_ollama_without_loading_sentence_transformers() -> None:
    embedder = create_embedder(
        CorpusConfig(
            embedding_provider="ollama",
            embedding_model="qwen3-embedding:0.6b",
            embedding_base_url="http://ollama.example",
        )
    )

    assert isinstance(embedder, OllamaEmbedder)
    assert embedder.model_id == "qwen3-embedding:0.6b"


def test_factory_selects_the_existing_local_qwen_embedder() -> None:
    embedder = create_embedder(
        CorpusConfig(
            embedding_provider="local",
            embedding_model="Qwen/Qwen3-Embedding-0.6B",
        )
    )

    assert isinstance(embedder, QwenEmbedder)
    assert embedder.model_id == "Qwen/Qwen3-Embedding-0.6B"
