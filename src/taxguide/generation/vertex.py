"""Native Vertex AI Gemini generation with lazy, renewable server-side ADC."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx

from taxguide.generation.base import ChatMessage
from taxguide.generation.openai_compatible import GenerationError


def vertex_origin(location: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", location):
        raise ValueError("Invalid Vertex AI location")
    if location == "global":
        host = "aiplatform.googleapis.com"
    elif location in {"eu", "us"}:
        host = f"aiplatform.{location}.rep.googleapis.com"
    else:
        host = f"{location}-aiplatform.googleapis.com"
    return f"https://{host}"


@dataclass(frozen=True)
class VertexAccess:
    token: str
    project: str | None = None
    quota_project: str | None = None


class ADCTokenSource:
    """Discover ADC and refresh expired tokens; never persist credentials in app settings."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._lock = Lock()
        self._credentials: Any = None
        self._project: str | None = None

    def __call__(self) -> VertexAccess:
        # Imports and credential discovery stay lazy: local generation needs no GCP account.
        import google.auth
        from google.auth.transport.requests import Request

        with self._lock:
            try:
                if self._credentials is None:
                    self._credentials, self._project = google.auth.default(
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )

                def request(*args: Any, **kwargs: Any) -> Any:
                    kwargs["timeout"] = self.timeout
                    return Request()(*args, **kwargs)

                if not self._credentials.valid:
                    self._credentials.refresh(request)
                token = self._credentials.token
                if not isinstance(token, str) or not token:
                    raise ValueError("ADC returned no token")
                return VertexAccess(token, self._project, self._credentials.quota_project_id)
            except Exception:
                raise GenerationError(
                    "Vertex AI authentication failed; verify server ADC and IAM"
                ) from None


class VertexAIGenerator:
    def __init__(
        self,
        model_id: str,
        *,
        project: str = "",
        location: str = "global",
        timeout: float = 180.0,
        structured_output: bool = True,
        thinking_budget: int | None = None,
        token_source: Callable[[], VertexAccess] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not re.fullmatch(r"gemini-[a-zA-Z0-9._-]+", model_id):
            raise ValueError("Vertex AI requires a Gemini publisher model ID")
        if not re.fullmatch(r"[a-zA-Z0-9-]{0,63}", project):
            raise ValueError("Invalid Vertex AI project")
        if timeout <= 0 or (thinking_budget is not None and thinking_budget < -1):
            raise ValueError("Invalid Vertex AI timeout or thinking budget")
        self._origin = vertex_origin(location)
        self._location = location
        self._project = project
        self._model_id = model_id
        self._structured = structured_output
        self._thinking_budget = thinking_budget
        self._tokens = token_source or ADCTokenSource(min(timeout, 30.0))
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, messages: list[ChatMessage], *, temperature: float, max_tokens: int) -> str:
        if not messages or not any(message["role"] != "system" for message in messages):
            raise ValueError("generation requires conversation messages")
        if not 0 <= temperature <= 2 or max_tokens <= 0:
            raise ValueError("Invalid generation temperature or max_tokens")
        access = self._tokens()
        project = self._project or access.project
        if not project or not re.fullmatch(r"[a-zA-Z0-9-]{1,63}", project):
            raise GenerationError("Configure a Vertex AI project or supply a project through ADC")
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if message["role"] == "assistant" else "user",
                    "parts": [{"text": message["content"]}],
                }
                for message in messages
                if message["role"] != "system"
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "candidateCount": 1,
            },
        }
        instructions = [
            {"text": message["content"]} for message in messages if message["role"] == "system"
        ]
        if instructions:
            payload["systemInstruction"] = {"parts": instructions}
        if self._structured:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if self._thinking_budget is not None:
            payload["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": self._thinking_budget,
            }
        headers = {"Authorization": f"Bearer {access.token}"}
        if access.quota_project:
            headers["x-goog-user-project"] = access.quota_project
        url = (
            f"{self._origin}/v1/projects/{project}/locations/{self._location}"
            f"/publishers/google/models/{self._model_id}:generateContent"
        )
        try:
            response = self._client.post(url, json=payload, headers=headers, follow_redirects=False)
            response.raise_for_status()
        except httpx.HTTPError:
            # Never include raw provider bodies, source context or credential-bearing requests.
            raise GenerationError(
                "Vertex AI request failed; verify API, IAM, model, region and quota"
            ) from None
        return _vertex_text(response)


def _vertex_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if payload.get("promptFeedback", {}).get("blockReason"):
            raise ValueError("Blocked prompt")
        candidate = payload["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Blocked or incomplete output")
        parts = candidate["content"]["parts"]
        text = "".join(
            part["text"]
            for part in parts
            if not part.get("thought", False) and isinstance(part.get("text"), str)
        )
        if not text.strip():
            raise ValueError("Empty output")
        return text
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise GenerationError("Vertex AI response was blocked, incomplete or malformed") from None
