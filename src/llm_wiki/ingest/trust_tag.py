"""Deterministic trust-tagging heuristic for claim provenance classification.

All logic is pure-function and stateless: given the same (content, claim_text,
source_reference) inputs the function always returns the same tag.  No LLM
calls are made.
"""

from __future__ import annotations

import re
from typing import Literal

_HEDGING = frozenset(
    (
        "possibly",
        "probably",
        "perhaps",
        "maybe",
        "likely",
        "unlikely",
        "could",
        "might",
        "may",
        "seems",
        "appears",
        "presumably",
        "arguably",
        "potentially",
        "supposedly",
    )
)

_REASONING_WORDS_LOWER = frozenset(
    (
        "therefore",
        "consequently",
        "means",
        "implies",
        "suggests",
        "thus",
        "hence",
        "so",
    )
)


def classify_claim_provenance(
    content: str,
    claim_text: str,
    source_reference: str | None = None,
) -> Literal["extracted", "inferred", "ambiguous"]:
    """Classify the epistemological provenance of a claim against its source.

    Parameters
    ----------
    content:
        The raw source text the claim was extracted from.
    claim_text:
        The claim statement to classify.
    source_reference:
        Optional pointer into *content* (e.g. "section 2, paragraph 1").
        Currently informational only.

    Returns
    -------
    ``"extracted"``
        Claim text appears verbatim (or 90 %+ match) in source content.
    ``"inferred"``
        Claim contains reasoning scaffolding (``therefore``, ``implies``,
        …) that is NOT present in the source.
    ``"ambiguous"``
        Claim is very short (< 15 chars), lacks a clear subject/predicate,
        or contains hedging language.
    """

    claim_lower = claim_text.strip().lower()

    # Ambiguous guard: very short claims
    if len(claim_text.strip()) < 15:
        return "ambiguous"

    # Hedge language
    words = set(re.findall(r"[a-z]+", claim_lower))
    if words & _HEDGING:
        return "ambiguous"

    # Inference detection: reasoning words whose phrasing is NOT in source
    for word in _REASONING_WORDS_LOWER:
        if word not in words:
            continue
        # Check the reasoning word is not literally in the content
        # (we do a whole-word check against normalized content)
        content_words = set(re.findall(r"[a-z]+", content.lower()))
        if word not in content_words:
            return "inferred"

    # Extracted: verbatim or 90%+ match check
    content_lower = content.lower()
    claim_stripped = claim_lower.strip()
    if claim_stripped in content_lower:
        return "extracted"

    # Fuzzy: check if claim is a substring with minor casing/punctuation diffs
    cleaned = re.sub(r"[^\w\s]", "", claim_stripped)
    if len(cleaned) >= 20:
        # sliding-window check (90% chars must be in content in order)
        if _fuzzy_contains(content_lower, cleaned):
            return "extracted"

    # Default to inferred for anything not verbatim — it took reasoning
    # to produce something not literally in the source.
    return "inferred"


def _fuzzy_contains(haystack: str, needle: str) -> bool:
    """Return True when *needle* appears in *haystack* with >= 90 % char match."""
    if len(needle) < 10:
        return False
    needle_len = len(needle)
    # Use sequential matching to approximate subsequence containment
    i = 0
    matches = 0
    for ch in haystack:
        if i < needle_len and ch == needle[i]:
            matches += 1
            i += 1
        if i == needle_len:
            break
    if i == needle_len:
        return True
    # Count how many chars matched
    ratio = matches / needle_len
    return ratio >= 0.9
