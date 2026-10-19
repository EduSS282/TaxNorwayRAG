"""Vertex HTTP and credentials are injected; no cloud calls or tokens are required."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from taxguide.config.models import GenerationConfig
from taxguide.generation.factory import create_generator
from taxguide.generation.openai_compatible import GenerationError
from taxguide.generation.vertex import ADCTokenSource, VertexAccess, VertexAIGenerator


def completion(text="{}", reason="STOP"):
    return {"candidates": [{"finishReason": reason, "content": {"parts": [{"text": text}]}}]}


def generator(handler, **kwargs):
    return VertexAIGenerator(
        "gemini-2.5-flash",
        token_source=lambda: VertexAccess("test-token", "adc-project", "quota-project"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def test_native_vertex_payload_roles_json_thinking_and_fixed_regional_destination():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=completion('{"answer":"grounded"}'))

    instance = generator(
        respond, project="explicit-project", location="europe-west4", thinking_budget=0
    )
    result = instance.generate(
        [
            {"role": "system", "content": "Ground only in the supplied context"},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Earlier answer"},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    request = requests[0]
    assert str(request.url) == (
        "https://europe-west4-aiplatform.googleapis.com/v1/projects/explicit-project/"
        "locations/europe-west4/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["x-goog-user-project"] == "quota-project"
    payload = json.loads(request.content)
    assert payload["systemInstruction"]["parts"][0]["text"].startswith("Ground")
    assert [item["role"] for item in payload["contents"]] == ["user", "model"]
    assert payload["generationConfig"] == {
        "temperature": 0.1,
        "maxOutputTokens": 4096,
        "candidateCount": 1,
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": 0},
    }
    assert result == '{"answer":"grounded"}'


def test_global_adc_project_and_thought_parts_are_not_exposed():
    def respond(request):
        assert request.url.host == "aiplatform.googleapis.com"
        assert "/projects/adc-project/locations/global/" in request.url.path
        payload = completion()
        payload["candidates"][0]["content"]["parts"] = [
            {"thought": True, "text": "private reasoning"},
            {"text": "{"},
            {"text": "}"},
        ]
        assert "thinkingConfig" not in json.loads(request.content)["generationConfig"]
        return httpx.Response(200, json=payload)

    assert (
        generator(respond).generate(
            [{"role": "user", "content": "Q"}], temperature=0.1, max_tokens=100
        )
        == "{}"
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"candidates": []},
        completion(reason="MAX_TOKENS"),
        completion(reason="SAFETY"),
        completion(text=""),
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [None]}}]},
    ],
)
def test_rejects_blocked_truncated_empty_and_malformed_responses(payload):
    instance = generator(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(GenerationError, match="blocked, incomplete or malformed"):
        instance.generate([{"role": "user", "content": "Q"}], temperature=0.1, max_tokens=100)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 302])
def test_http_errors_are_sanitized_and_not_retried_or_redirected(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status, text="secret-token private context", headers={"Location": "https://evil.test"}
        )

    with pytest.raises(GenerationError) as error:
        generator(respond).generate(
            [{"role": "user", "content": "Q"}], temperature=0.1, max_tokens=100
        )
    assert "secret-token" not in str(error.value)
    assert len(requests) == 1


def test_missing_adc_project_fails_without_request():
    instance = VertexAIGenerator("gemini-2.5-flash", token_source=lambda: VertexAccess("token"))
    with pytest.raises(GenerationError, match="project"):
        instance.generate([{"role": "user", "content": "Q"}], temperature=0.1, max_tokens=100)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"project": "project/path"},
        {"location": "global.evil.test"},
        {"timeout": 0},
        {"thinking_budget": -2},
    ],
)
def test_invalid_vertex_configuration_cannot_change_destination(kwargs):
    with pytest.raises(ValueError):
        VertexAIGenerator("gemini-2.5-flash", **kwargs)


def test_factory_is_lazy_and_invalid_publisher_models_are_rejected(monkeypatch):
    monkeypatch.setattr(
        "google.auth.default", Mock(side_effect=AssertionError("no discovery at import"))
    )
    instance = create_generator(GenerationConfig(provider="vertex_ai", model="gemini-2.5-flash"))
    assert isinstance(instance, VertexAIGenerator)
    assert instance.model_id == "gemini-2.5-flash"
    with pytest.raises(ValueError, match="Gemini"):
        GenerationConfig(provider="vertex_ai", model="../../other-model")


def test_adc_discovery_cached_tokens_refresh_only_when_expired_and_timeout_is_bounded(monkeypatch):
    credentials = SimpleNamespace(valid=False, token=None, quota_project_id="quota")
    calls = []

    def refresh(request):
        calls.append(True)
        request("http://credentials.invalid", timeout=999)
        credentials.token = f"token-{len(calls)}"
        credentials.valid = True

    credentials.refresh = refresh
    discover = Mock(return_value=(credentials, "adc-project"))
    transport = Mock(return_value=object())
    monkeypatch.setattr("google.auth.default", discover)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: transport)
    source = ADCTokenSource(timeout=3)
    assert source().token == "token-1"
    assert source().token == "token-1"
    credentials.valid = False
    assert source().token == "token-2"
    assert discover.call_count == 1
    assert transport.call_args.kwargs["timeout"] == 3


def test_adc_failure_does_not_leak_credential_paths_or_tokens(monkeypatch):
    monkeypatch.setattr(
        "google.auth.default", Mock(side_effect=RuntimeError("secret /private/key.json"))
    )
    with pytest.raises(GenerationError) as error:
        ADCTokenSource()()
    assert "secret" not in str(error.value)
    assert "/private" not in str(error.value)
