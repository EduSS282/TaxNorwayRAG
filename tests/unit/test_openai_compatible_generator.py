import json
from collections.abc import Callable

import httpx
import pytest

from taxguide.generation.base import ChatMessage
from taxguide.generation.openai_compatible import GenerationError, OpenAICompatibleGenerator


def test_openai_compatible_generator_sends_openai_chat_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Grounded answer"}}]})

    generator = OpenAICompatibleGenerator(
        "http://localhost:8000/",
        "Qwen/Qwen3-4B-Instruct-2507",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = generator.generate(
        [{"role": "user", "content": "When is the tax deadline?"}],
        temperature=0.1,
        max_tokens=1000,
    )

    assert result == "Grounded answer"
    assert str(requests[0].url) == "http://localhost:8000/v1/chat/completions"
    assert json.loads(requests[0].content) == {
        "model": "Qwen/Qwen3-4B-Instruct-2507",
        "messages": [{"role": "user", "content": "When is the tax deadline?"}],
        "temperature": 0.1,
        "max_tokens": 1000,
    }


def test_openai_compatible_generator_requests_json_object_output_when_configured() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    generator = OpenAICompatibleGenerator(
        "http://localhost:8000",
        "test-model",
        structured_output=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    generator.generate(_messages(), temperature=0.1, max_tokens=10)

    assert json.loads(requests[0].content)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": 3}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}),
    ],
)
def test_openai_compatible_generator_rejects_malformed_responses(response: httpx.Response) -> None:
    generator = _generator(lambda request: response)

    with pytest.raises(GenerationError, match="generation response"):
        generator.generate(_messages(), temperature=0.1, max_tokens=10)


def test_openai_compatible_generator_wraps_http_errors() -> None:
    generator = _generator(lambda request: httpx.Response(503, request=request))

    with pytest.raises(GenerationError, match="generation request failed"):
        generator.generate(_messages(), temperature=0.1, max_tokens=10)


@pytest.mark.parametrize(
    ("messages", "temperature", "max_tokens", "message"),
    [
        ([], 0.1, 1, "messages"),
        ([{"role": "user", "content": "Question"}], -0.1, 1, "temperature"),
        ([{"role": "user", "content": "Question"}], 0.1, 0, "max_tokens"),
    ],
)
def test_openai_compatible_generator_validates_generation_arguments(
    messages: list[ChatMessage], temperature: float, max_tokens: int, message: str
) -> None:
    generator = _generator(lambda request: httpx.Response(200))

    with pytest.raises(ValueError, match=message):
        generator.generate(messages, temperature=temperature, max_tokens=max_tokens)


@pytest.mark.parametrize(
    ("base_url", "model_id", "timeout"),
    [("", "model", 1.0), ("http://localhost", "", 1.0), ("http://localhost", "model", 0.0)],
)
def test_openai_compatible_generator_validates_configuration(
    base_url: str, model_id: str, timeout: float
) -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleGenerator(base_url, model_id, timeout=timeout)


def _generator(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAICompatibleGenerator:
    return OpenAICompatibleGenerator(
        "http://localhost:8000",
        "test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _messages() -> list[ChatMessage]:
    return [{"role": "user", "content": "Question"}]
