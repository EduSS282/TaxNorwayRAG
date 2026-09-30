"""Adapter for local servers exposing OpenAI chat-completions semantics."""

from typing import Any, cast

import httpx

from taxguide.generation.base import ChatMessage


class GenerationError(RuntimeError):
    """A local generation backend could not produce a usable completion."""


class OpenAICompatibleGenerator:
    """Generate text through a local ``/v1/chat/completions`` endpoint."""

    def __init__(
        self,
        base_url: str,
        model_id: str,
        *,
        timeout: float = 120.0,
        structured_output: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("generation base_url must not be empty")
        if not model_id.strip():
            raise ValueError("generation model_id must not be empty")
        if timeout <= 0:
            raise ValueError("generation timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._structured_output = structured_output
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not messages:
            raise ValueError("generation messages must not be empty")
        if not 0 <= temperature <= 2:
            raise ValueError("generation temperature must be between 0 and 2")
        if max_tokens <= 0:
            raise ValueError("generation max_tokens must be positive")
        try:
            payload: dict[str, Any] = {
                "model": self._model_id,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if self._structured_output:
                payload["response_format"] = {"type": "json_object"}
            response = self._client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise GenerationError(f"generation request failed: {error}") from error
        return _completion_content(response)


def _completion_content(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except (TypeError, ValueError) as error:
        raise GenerationError("generation response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise GenerationError("generation response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GenerationError("generation response must contain a non-empty choices list")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise GenerationError("generation response choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise GenerationError("generation response choice must contain text message content")
    content = cast(str, message["content"])
    if not content.strip():
        raise GenerationError("generation response message content must not be blank")
    return content
