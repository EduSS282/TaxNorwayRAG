from taxguide.chunking.tokenizer import Tokenizer, WhitespaceTokenizer


def test_whitespace_tokenizer_counts_unicode_and_normalizes_separators() -> None:
    tokenizer = WhitespaceTokenizer()

    assert tokenizer.tokenize("  Norwegian\t tax\n  return ") == ("Norwegian", "tax", "return")
    assert tokenizer.count_tokens("Café i Norge") == 3
    assert tokenizer.count_tokens("") == 0


def test_whitespace_tokenizer_detokenizes_without_empty_tokens() -> None:
    tokenizer = WhitespaceTokenizer()

    assert tokenizer.detokenize(("Tax", "return")) == "Tax return"
    assert tokenizer.detokenize(()) == ""


def test_tokenizer_is_replaceable_without_protocol_inheritance() -> None:
    class CharacterTokenizer:
        def tokenize(self, text: str) -> tuple[str, ...]:
            return tuple(text)

        def detokenize(self, tokens: tuple[str, ...]) -> str:
            return "".join(tokens)

        def count_tokens(self, text: str) -> int:
            return len(text)

    tokenizer: Tokenizer = CharacterTokenizer()
    assert tokenizer.count_tokens("tax") == 3
