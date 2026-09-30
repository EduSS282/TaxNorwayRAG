import json

import httpx
import pytest

from taxguide.domain.exceptions import EmbeddingError
from taxguide.embeddings.ollama import OllamaEmbedder


def client_with_response(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: response))


def test_ollama_embedder_posts_a_batch_to_the_embed_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[1, 2], [3, 4]]})

    embedder = OllamaEmbedder(
        "http://ollama.example/",
        "qwen3-embedding:0.6b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert embedder.embed_documents(["first", "second"]) == [(1.0, 2.0), (3.0, 4.0)]
    assert requests[0].url == "http://ollama.example/api/embed"
    assert json.loads(requests[0].content) == {
        "model": "qwen3-embedding:0.6b",
        "input": ["first", "second"],
    }


def test_ollama_embedder_embeds_a_query_with_the_shared_batch_logic() -> None:
    embedder = OllamaEmbedder(
        "http://ollama.example",
        "test-model",
        client=client_with_response(httpx.Response(200, json={"embeddings": [[0.5, 0.25]]})),
    )

    assert embedder.embed_query("When is the tax return due?") == (0.5, 0.25)
    assert embedder.dimension == 2


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "missing an embeddings list"),
        ({"embeddings": []}, "returned no embeddings"),
        ({"embeddings": [[1, "bad"]]}, "non-numeric"),
        ({"embeddings": [[]]}, "empty or invalid vector"),
    ],
)
def test_ollama_embedder_rejects_malformed_responses(payload: object, message: str) -> None:
    embedder = OllamaEmbedder(
        "http://ollama.example",
        "test-model",
        client=client_with_response(httpx.Response(200, json=payload)),
    )

    with pytest.raises(EmbeddingError, match=message):
        embedder.embed_documents(["text"])


def test_ollama_embedder_reports_http_failures() -> None:
    embedder = OllamaEmbedder(
        "http://ollama.example",
        "test-model",
        client=client_with_response(httpx.Response(503, text="unavailable")),
    )

    with pytest.raises(EmbeddingError, match="Ollama embedding request failed"):
        embedder.embed_documents(["text"])


def test_ollama_embedder_rejects_a_wrong_number_of_vectors() -> None:
    embedder = OllamaEmbedder(
        "http://ollama.example",
        "test-model",
        client=client_with_response(httpx.Response(200, json={"embeddings": [[1, 2]]})),
    )

    with pytest.raises(EmbeddingError, match="1 embeddings for 2 input texts"):
        embedder.embed_documents(["first", "second"])


def test_ollama_embedder_rejects_inconsistent_vector_dimensions() -> None:
    embedder = OllamaEmbedder(
        "http://ollama.example",
        "test-model",
        client=client_with_response(httpx.Response(200, json={"embeddings": [[1, 2], [3]]})),
    )

    with pytest.raises(EmbeddingError, match="inconsistent dimensions"):
        embedder.embed_documents(["first", "second"])
