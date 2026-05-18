"""Synthesis engine — async generator for LLM-based and heuristic summarization.

Architectural invariant: synthesize() MUST be an async generator. This enables
future REST streaming. Never convert to a synchronous function.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SynthesisChunk:
    """A chunk of synthesized text."""

    text: str
    is_final: bool = False
    sources: list[str] = field(default_factory=list)


@dataclass
class DeepQueryResult:
    """Result of a deep query operation."""

    chunks: list[SynthesisChunk]
    timed_out: bool
    partial: bool
    was_heuristic: bool = False


async def _synthesize_heuristic(
    query: str,
    pages: list,
) -> AsyncGenerator[SynthesisChunk, None]:
    """Heuristic fallback: pages sorted by confidence, concatenated.

    Sprint 1 implementation. Also serves as the permanent fallback when
    LLM synthesis fails in later epics.
    """
    for page in sorted(
        pages,
        key=lambda p: getattr(p, "confidence", 0.0),
        reverse=True,
    ):
        yield SynthesisChunk(
            text=f"## {getattr(page, 'title', page)}\n\n{getattr(page, 'content', '')}",
            sources=[getattr(page, "id", str(page))],
        )
    yield SynthesisChunk(text="", is_final=True)


async def _synthesize_llm(
    query: str,
    pages: list,
) -> AsyncGenerator[SynthesisChunk, None]:
    """LLM-based synthesis. Implemented in Epic 2.

    Raises ``NotImplementedError`` until then.
    """
    raise NotImplementedError("LLM synthesis not yet implemented — Epic 2")
    yield  # makes this an async generator


async def synthesize(
    query: str,
    pages: list,
    llm_extraction: bool = False,
) -> AsyncGenerator[SynthesisChunk, None]:
    """Single entry point for synthesis. Handles fallback internally.

    If ``llm_extraction`` is ``False`` or the LLM call fails, falls back
    to heuristic silently (with error logging on unexpected LLM failure).
    Callers check ``was_heuristic`` on :class:`DeepQueryResult` to know
    which path ran.
    """
    if llm_extraction:
        try:
            async for chunk in _synthesize_llm(query, pages):
                yield chunk
            return
        except NotImplementedError:
            pass  # expected until Epic 2
        except Exception as e:
            logger.error("LLM synthesis failed, falling back to heuristic: %s", e)

    async for chunk in _synthesize_heuristic(query, pages):
        yield chunk


async def run_deep_query(
    query: str,
    pages: list,
    llm_extraction: bool = False,
    timeout: float = 30.0,
) -> DeepQueryResult:
    """Run a deep query with optional LLM synthesis and timeout.

    Args:
        query: The query string.
        pages: List of page metadata dicts.
        llm_extraction: Whether to attempt LLM-based synthesis.
        timeout: Timeout in seconds (default 30).

    Returns:
        A :class:`DeepQueryResult` with the synthesis output.
    """
    chunks: list[SynthesisChunk] = []
    timed_out = False
    was_heuristic = not llm_extraction
    try:
        async with asyncio.timeout(timeout):
            async for chunk in synthesize(query, pages, llm_extraction=llm_extraction):
                chunks.append(chunk)
    except TimeoutError:
        timed_out = True
        was_heuristic = True

    # Determine was_heuristic: true if flag was off, or if no non-final chunks
    if llm_extraction and chunks:
        has_content = any(not c.is_final for c in chunks)
        if not has_content:
            was_heuristic = True

    return DeepQueryResult(
        chunks=chunks,
        timed_out=timed_out,
        partial=timed_out,
        was_heuristic=was_heuristic,
    )
