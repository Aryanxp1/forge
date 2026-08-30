"""In-memory DERIVED inverted index for FORGE.

Storage is the source of truth; this index is derived data and can be
rebuilt from storage at any time:

    Storage -> scan documents -> tokenize -> build index

Core data structure: term -> set of document IDs.

    python   -> {1, 4, 9}
    storage  -> {2, 4}
    search   -> {1, 4, 7}

Posting lists are Python sets, so a term repeated inside one document
maps to a single document ID:

    Document "python python python"  ->  python -> {1}, never {1, 1, 1}

Term frequency within a document (doc_id -> Counter) is also tracked so
a later phase can compute TF-IDF ranking. No ranking is implemented yet.
"""

from collections import Counter
from typing import Iterable, Iterator

from .tokenizer import tokenize


class InvertedIndex:
    """In-memory inverted index: term -> set of document IDs.

    Documents are identified by their unique integer doc_id. Adding the
    same doc_id again replaces its previous postings (the doc is
    re-indexed from scratch), which keeps this derived structure
    self-consistent during rebuilds.
    """

    def __init__(self) -> None:
        self._postings: dict[str, set[int]] = {}
        self._doc_terms: dict[int, Counter] = {}

    def add_document(self, doc_id: int, text: str) -> None:
        """Tokenize ``text`` and index all resulting terms for ``doc_id``.

        Tokens are normalized through :func:`forge.tokenizer.tokenize`
        (lowercased, split on non-alphanumerics, stopwords removed).
        """
        self.add_tokens(doc_id, tokenize(text))

    def add_tokens(self, doc_id: int, tokens: Iterable[str]) -> None:
        """Index an already-normalized token list for ``doc_id``.

        Tokens are stored verbatim; callers that pass raw text should
        use :meth:`add_document` so the tokenizer runs first.

        Raises:
            TypeError: If ``tokens`` is not iterable of str.
        """
        if doc_id in self._doc_terms:
            self._remove_document(doc_id)

        counts: Counter = Counter(tokens)
        for term in counts:
            self._postings.setdefault(term, set()).add(doc_id)
        self._doc_terms[doc_id] = counts

    def _remove_document(self, doc_id: int) -> None:
        """Remove every posting belonging to ``doc_id``."""
        for term in self._doc_terms[doc_id]:
            posting = self._postings[term]
            posting.discard(doc_id)
            if not posting:
                del self._postings[term]
        del self._doc_terms[doc_id]

    def term_documents(self, term: str) -> frozenset[int]:
        """Document IDs containing ``term`` (empty frozenset if unknown)."""
        return frozenset(self._postings.get(term, ()))

    def has_term(self, term: str) -> bool:
        """True if at least one document contains ``term``."""
        return term in self._postings

    def term_count(self) -> int:
        """Number of distinct terms in the index."""
        return len(self._postings)

    def document_count(self) -> int:
        """Number of documents in the index."""
        return len(self._doc_terms)

    def document_frequency(self, term: str) -> int:
        """Number of documents containing ``term`` (0 if unknown)."""
        return len(self._postings.get(term, ()))

    def token_frequency(self, doc_id: int, term: str) -> int:
        """Count of ``term`` occurrences inside ``doc_id`` (0 if absent)."""
        counts = self._doc_terms.get(doc_id)
        if counts is None:
            return 0
        return int(counts.get(term, 0))

    def documents(self) -> frozenset[int]:
        """All indexed document IDs."""
        return frozenset(self._doc_terms)

    def terms(self) -> Iterator[str]:
        """Iterate over all distinct indexed terms."""
        return iter(self._postings)