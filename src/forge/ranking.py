"""Deterministic TF-IDF ranking over the derived inverted index.

This module scores and ranks the candidate documents returned by
:mod:`forge.search`. It does not perform candidate selection itself —
AND/OR matching is handled by ``search_and``/``search_or``; this module
only orders the candidates.

Formula (documented, single definition — no mixing):

    TF(term, doc) = count of ``term`` occurrences in ``doc``
                    (raw term frequency, from InvertedIndex.token_frequency)

    IDF(term) = log(N / df)
        N  = total number of indexed documents (InvertedIndex.document_count)
        df = number of documents containing ``term`` (document_frequency)

    Score(doc, query) = Σ  TF(doc, term) × IDF(term)
                         over the UNIQUE query terms present in ``doc``

The query is treated as a SET of normalized terms: repeating a query term
does not multiply the score. Unknown terms contribute 0.

Ranking order:
    1. Higher TF-IDF score first.
    2. Document ID ascending as the deterministic tie-breaker.

All math uses the standard ``math`` module (natural log).
"""

import math
from typing import List

from .index import InvertedIndex
from .search import search_and, search_or


def term_frequency(index: InvertedIndex, doc_id: int, term: str) -> int:
    """Raw count of ``term`` occurrences inside ``doc_id`` (0 if absent)."""
    return index.token_frequency(doc_id, term)


def document_frequency(index: InvertedIndex, term: str) -> int:
    """Number of documents containing ``term`` (0 if unknown)."""
    return index.document_frequency(term)


def inverse_document_frequency(index: InvertedIndex, term: str) -> float:
    """Compute IDF(term) = log(N / df).

    Returns 0.0 when the term is unknown (df == 0) or when the index is
    empty (N == 0), so unknown terms contribute nothing to the score.
    """
    n = index.document_count()
    df = index.document_frequency(term)
    if n == 0 or df == 0:
        return 0.0
    return math.log(n / df)


def score_document(index: InvertedIndex, doc_id: int, terms: List[str]) -> float:
    """Compute the TF-IDF score of ``doc_id`` against ``terms``.

    Each unique query term contributes TF × IDF once. Unknown terms add 0.
    """
    unique_terms = set(terms)
    total = 0.0
    for term in unique_terms:
        tf = index.token_frequency(doc_id, term)
        if tf == 0:
            continue
        idf = inverse_document_frequency(index, term)
        total += tf * idf
    return total


def rank_documents(index: InvertedIndex, doc_ids: List[int], terms: List[str]) -> List[int]:
    """Rank ``doc_ids`` by TF-IDF score (descending), doc-ID tie-break.

    The result is deterministic: equal scores resolve to ascending doc ID.
    An empty candidate list or empty terms yield ``[]``.
    """
    if not doc_ids or not terms:
        return []
    scored = [(doc_id, score_document(index, doc_id, terms)) for doc_id in doc_ids]
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return [doc_id for doc_id, _ in scored]


def search_ranked(
    index: InvertedIndex,
    query: str,
    mode: str = "and",
) -> List[int]:
    """Search with TF-IDF ranking.

    Candidate selection uses the existing AND/OR semantics from
    :mod:`forge.search`; only the ordering changes.

    Args:
        index: The inverted index to query.
        query: Raw query text (any case; punctuation is a separator).
        mode: ``"and"`` (default) or ``"or"``.

    Returns:
        Document IDs ranked by descending TF-IDF score, with ascending
        document ID as the tie-breaker. Empty query yields ``[]``.

    Raises:
        ValueError: If ``mode`` is neither ``"and"`` nor ``"or"``.
    """
    from .tokenizer import tokenize

    terms = tokenize(query)
    if not terms:
        return []

    if mode == "and":
        candidates = search_and(index, terms)
    elif mode == "or":
        candidates = search_or(index, terms)
    else:
        raise ValueError(f"unknown search mode {mode!r}; expected 'and' or 'or'")

    return rank_documents(index, candidates, terms)
