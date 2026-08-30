"""Index rebuild and storage <-> index consistency validation.

LOCKED PRINCIPLE:

    STORAGE = SOURCE OF TRUTH
    INDEX   = DERIVED DATA

The inverted index holds no authoritative state, so it can always be
thrown away and reconstructed:

    Storage -> iter_records() -> decode UTF-8 -> tokenize -> InvertedIndex

Text encoding
-------------
Storage payloads are UTF-8 encoded document content, as documented in
records.py ("PAYLOAD: N bytes, UTF-8 encoded document content"). This
module uses that same convention and never guesses another codec. A
payload that is not valid UTF-8 raises PayloadDecodeError rather than
being silently dropped or mangled.

Note on naming
--------------
recovery.validate_consistency(wal_path, storage) checks storage against
the WAL. This module's validate_consistency(storage, index) checks the
derived index against storage. They validate different pairs of layers
and deliberately live in separate modules.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .index import InvertedIndex
from .storage import Storage
from .tokenizer import tokenize

#: Payload byte encoding used by FORGE storage (see records.py).
TEXT_ENCODING = 'utf-8'


class PayloadDecodeError(Exception):
    """A stored payload is not valid text in TEXT_ENCODING."""


def decode_payload(doc_id: int, payload: bytes) -> str:
    """Decode a stored payload to text using the project encoding.

    Raises:
        PayloadDecodeError: If the bytes are not valid UTF-8. The error
            is explicit; corrupt text is never silently substituted.
    """
    try:
        return payload.decode(TEXT_ENCODING)
    except UnicodeDecodeError as exc:
        raise PayloadDecodeError(
            f"document {doc_id} payload is not valid {TEXT_ENCODING}: {exc}"
        ) from exc


def rebuild_index(storage: Storage) -> InvertedIndex:
    """Build a fresh InvertedIndex from every document in ``storage``.

    This is the single indexing path in FORGE: it reuses
    Storage.iter_records() for scanning and InvertedIndex.add_document()
    for tokenizing, so no scanning or indexing logic is duplicated.

    Cost is O(total tokens in storage). There is no cache, no persistent
    index file and no incremental indexing in V1.

    Args:
        storage: Open storage to read documents from.

    Returns:
        A newly built index. Empty storage yields an empty index.

    Raises:
        PayloadDecodeError: If a stored payload is not valid UTF-8.
        StorageCorruptedError: Propagated from Storage.iter_records().
    """
    index = InvertedIndex()
    for doc_id, payload in storage.iter_records():
        index.add_document(doc_id, decode_payload(doc_id, payload))
    return index


@dataclass
class IndexConsistencyReport:
    """Result of validating an index against storage.

    Every field is computed by comparing the index to an independent
    re-derivation from storage, never to the index itself. See
    :func:`validate_consistency`.
    """

    storage_doc_count: int
    index_doc_count: int
    #: Doc IDs present in storage but absent from the index.
    missing_docs: List[int] = field(default_factory=list)
    #: Doc IDs present in the index but absent from storage.
    extra_docs: List[int] = field(default_factory=list)
    #: term -> doc IDs stored with that term but missing from its posting.
    missing_postings: Dict[str, List[int]] = field(default_factory=dict)
    #: term -> doc IDs in its posting but NOT actually stored with the term.
    extra_postings: Dict[str, List[int]] = field(default_factory=dict)
    #: (doc_id, term, expected_freq, actual_freq) for frequency mismatches.
    term_frequency_mismatches: List[Tuple[int, str, int, int]] = field(
        default_factory=list
    )
    #: Terms present in the index but not derivable from any stored document.
    extra_terms: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True iff the index fully agrees with storage."""
        return (
            not self.missing_docs
            and not self.extra_docs
            and not self.missing_postings
            and not self.extra_postings
            and not self.term_frequency_mismatches
            and not self.extra_terms
        )


def validate_consistency(storage: Storage, index: InvertedIndex) -> IndexConsistencyReport:
    """Verify that ``index`` matches an independent rebuild from ``storage``.

    The reference posting lists and per-document term frequencies are
    recomputed from scratch by scanning storage and running the standard
    tokenizer. The supplied ``index`` is then compared field by field
    against that reference. Because the reference comes from STORAGE and
    not from the index, the check will detect a self-consistent-looking
    but wrong index.

    Missing/extra doc IDs, missing/extra posting entries, wrong term
    frequencies and spurious index terms are all reported. Inconsistencies
    are recorded in the report; no index or storage state is mutated.

    Args:
        storage: Open storage (source of truth).
        index: Derived index to validate.

    Returns:
        An IndexConsistencyReport whose ``ok`` property is True only when
        every check passes.

    Raises:
        PayloadDecodeError: If a stored payload is not valid UTF-8.
        StorageCorruptedError: Propagated from Storage.iter_records().
    """
    # --- Independently derive the expected state from storage. ---
    expected_postings: Dict[str, set] = {}
    expected_freqs: Dict[Tuple[int, str], int] = {}

    for doc_id, payload in storage.iter_records():
        text = decode_payload(doc_id, payload)
        for term, count in Counter(tokenize(text)).items():
            expected_postings.setdefault(term, set()).add(doc_id)
            key = (doc_id, term)
            expected_freqs[key] = expected_freqs.get(key, 0) + count

    report = IndexConsistencyReport(
        storage_doc_count=len(storage),
        index_doc_count=index.document_count(),
    )

    # --- Document-ID level checks ---
    storage_ids = set(storage.doc_ids)
    index_ids = set(index.documents())
    report.missing_docs = sorted(storage_ids - index_ids)
    report.extra_docs = sorted(index_ids - storage_ids)

    # --- Term posting + frequency checks ---
    for term in sorted(expected_postings):
        expected_docs = expected_postings[term]
        actual_docs = set(index.term_documents(term))
        if actual_docs != expected_docs:
            if not actual_docs:
                report.missing_postings[term] = sorted(expected_docs)
            elif not expected_docs:
                report.extra_postings[term] = sorted(actual_docs)
            else:
                report.missing_postings[term] = sorted(expected_docs - actual_docs)
                report.extra_postings[term] = sorted(actual_docs - expected_docs)
        for doc_id in expected_docs & actual_docs:
            expected_freq = expected_freqs[(doc_id, term)]
            actual_freq = index.token_frequency(doc_id, term)
            if actual_freq != expected_freq:
                report.term_frequency_mismatches.append(
                    (doc_id, term, expected_freq, actual_freq)
                )

    # --- Terms the index knows about that storage never produced ---
    for term in sorted(index.terms()):
        if term not in expected_postings:
            report.extra_terms.append(term)
            report.extra_postings[term] = sorted(index.term_documents(term))

    return report
