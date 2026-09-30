from taxguide.config.models import AppConfig
from taxguide.indexing.signature import index_signature


def test_signature_changes_with_chunking_and_embedding_model() -> None:
    settings = AppConfig()
    baseline = index_signature(settings, "embedder-a")
    assert index_signature(settings, "embedder-a") == baseline
    assert index_signature(settings, "embedder-b") != baseline
    changed = settings.model_copy(
        update={"corpus": settings.corpus.model_copy(update={"max_tokens": 256})}
    )
    assert index_signature(changed, "embedder-a") != baseline
