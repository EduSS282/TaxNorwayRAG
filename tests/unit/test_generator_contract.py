"""Tests for the replaceable generation-backend contract."""

from taxguide.generation.base import ChatMessage, Generator


def test_generator_contract_is_replaceable() -> None:
    class EchoGenerator:
        model_id = "test"

        def generate(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float,
            max_tokens: int,
        ) -> str:
            assert temperature == 0.1
            assert max_tokens == 20
            return messages[-1]["content"]

    generator: Generator = EchoGenerator()

    assert generator.model_id == "test"
    assert generator.generate(
        [
            {"role": "system", "content": "Use the supplied evidence."},
            {"role": "user", "content": "What is the deadline?"},
        ],
        temperature=0.1,
        max_tokens=20,
    ) == "What is the deadline?"
