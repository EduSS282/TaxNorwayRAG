"""Stable contract for text-generation backends."""

from typing import Literal, Protocol, TypedDict

type ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(TypedDict):
    """One complete chat message accepted by a generator backend."""

    role: ChatRole
    content: str


class Generator(Protocol):
    """Generates text from a fully prepared sequence of chat messages."""

    @property
    def model_id(self) -> str: ...

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str: ...
