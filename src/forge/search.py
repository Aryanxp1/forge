"""AND/OR query evaluation over the derived inverted index.

V1 supports exactly two operators:

- AND: documents containing ALL query terms (posting-list intersection)
- OR:  documents containing AT LEAST ONE query term (posting-list union)

Determinism contract:
    Results are lists of document IDs sorted in ascending numeric order.
    Posting lists are sets whose iteration order is an implementation
    detail; this module never relies on it.

Empty-query semantics (V1):
    Zero query terms yield an empty result for both operators. Pure set
    algebra would define AND over zero terms as "every document"; FORGE
    uses the safer, less surprising rule: no terms -> no results.

Term contract:
    search_and() and search_or() expect already-normalized terms, exactly
    as produced by :func:`forge.tokenizer.tokenize`. The high-level
    :func:`search` entry point accepts raw query text and normalizes it
    first.

No ranking is implemented in this phase: AND results all satisfy the
same constraint, and OR results are ordered by document ID. TF-IDF (or
another deterministic ranking) is deferred to a later phase by design.
"""

from typing import Iterable, List

from .index import InvertedIndex
from .tokenizer import tokenize

MODE_AND = "and"
MODE_OR = "or"


def search_and(index: InvertedIndex, terms: Iterable[str]) -> List[int]:
    """Return document IDs (ascending) whose documents contain ALL terms.

    A single unknown term empties the intersection, so evaluation stops
    as soon as the candidate set becomes empty.

    Args:
        index: The inverted index to query.
        terms: Normalized terms (as produced by ``tokenize``).

    Returns:
        Sorted list of document IDs. Empty term list yields ``[]``.
    """
    term_list = list(terms)
    if not term_list:
        return []

    result: set = set(index.term_documents(term_list[0]))
    for term in term_list[1:]:
        if not result:
            break
        result &= index.term_documents(term)
    return sorted(result)


def search_or(index: InvertedIndex, terms: Iterable[str]) -> List[int]:
    """Return document IDs (ascending) containing AT LEAST ONE term.

    Unknown terms contribute nothing to the union.

    Args:
        index: The inverted index to query.
        terms: Normalized terms (as produced by ``tokenize``).

    Returns:
        Sorted list of document IDs without duplicates. Empty term list
        yields ``[]``.
    """
    result: set = set()
    for term in terms:
        result |= index.term_documents(term)
    return sorted(result)


def search(index: InvertedIndex, query: str, mode: str = MODE_AND) -> List[int]:
    """Normalize ``query`` with the standard tokenizer and evaluate it.

    Args:
        index: The inverted index to query.
        query: Raw query text (any case; punctuation is a separator).
        mode: ``MODE_AND`` (default) or ``MODE_OR``.

    Returns:
        Document IDs in ascending order.

    Raises:
        ValueError: If ``mode`` is neither ``"and"`` nor ``"or"``.
    """
    if mode == MODE_AND:
        return search_and(index, tokenize(query))
    if mode == MODE_OR:
        return search_or(index, tokenize(query))
    raise ValueError(
        f"unknown search mode {mode!r}; expected {MODE_AND!r} or {MODE_OR!r}"
    )