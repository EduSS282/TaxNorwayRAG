from collections.abc import Sequence
from typing import overload

from taxguide.embeddings.qwen import DEFAULT_QWEN_MODEL_ID, QwenEmbedder


class FakeSentenceTransformer:
    def __init__(self) -> None:
        self.calls: list[str | list[str]] = []

    @overload
    def encode(
        self,
        sentences: str,
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Sequence[float]: ...

    @overload
    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Sequence[Sequence[float]]: ...

    def encode(
        self,
        sentences: str | list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Sequence[Sequence[float]] | Sequence[float]:
        assert normalize_embeddings is True
        assert show_progress_bar is False
        self.calls.append(sentences)
        if isinstance(sentences, str):
            return [0.5, 0.25]
        return [[float(index), 0.25] for index, _ in enumerate(sentences)]


def test_qwen_embedder_uses_default_model_and_loads_it_lazily() -> None:
    model = FakeSentenceTransformer()
    requested_models: list[str] = []

    def load_model(model_id: str) -> FakeSentenceTransformer:
        requested_models.append(model_id)
        return model

    embedder = QwenEmbedder(model_factory=load_model)

    assert embedder.model_id == DEFAULT_QWEN_MODEL_ID
    assert requested_models == []
    assert embedder.embed_documents(["first", "second"]) == [(0.0, 0.25), (1.0, 0.25)]
    assert requested_models == [DEFAULT_QWEN_MODEL_ID]
    assert model.calls == [["first", "second"]]


def test_qwen_embedder_embeds_queries_and_records_the_dimension() -> None:
    embedder = QwenEmbedder(model_factory=lambda _: FakeSentenceTransformer())

    assert embedder.embed_query("When is the tax return due?") == (0.5, 0.25)
    assert embedder.dimension == 2
