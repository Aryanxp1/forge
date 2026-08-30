"""Deterministic V1 tokenizer for FORGE.

Documented behavior:

1. Convert text to lowercase.
2. Split on non-alphanumeric characters. Each maximal run of characters
   where ``str.isalnum()`` is True becomes one token; everything else is
   a separator (whitespace, punctuation, symbols, emoji).
3. Remove tokens in the small built-in stopword set (``STOPWORDS``).
4. Return normalized tokens in document order.

Examples:
    "Python, Storage & Search!" -> ["python", "storage", "search"]
    "HELLO world   123"         -> ["hello", "world", "123"]

Unicode-safe: ``str.isalnum()`` recognizes Unicode letters and digits,
so accented and non-ASCII text is tokenized without any NLP tooling.
Numbers are valid tokens.

Tokenization is deterministic: the same input always produces the same
list of tokens.
"""

STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'have', 'he', 'her', 'his', 'i', 'in', 'is', 'it', 'its',
    'of', 'on', 'or', 'she', 'that', 'the', 'their', 'them', 'this',
    'to', 'was', 'we', 'were', 'will', 'with', 'you', 'your',
})


def tokenize(text: str) -> list[str]:
    """Normalize ``text`` into a list of lowercase, stopword-free tokens.

    Args:
        text: Document text as str.

    Returns:
        List of tokens. Empty input, punctuation-only input, or input
        containing only stopwords yields an empty list.

    Raises:
        TypeError: If ``text`` is not a str.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"tokenize() requires str, got {type(text).__name__}"
        )

    tokens: list[str] = []
    current: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.append(''.join(current))
            current = []
    if current:
        tokens.append(''.join(current))

    return [t for t in tokens if t not in STOPWORDS]