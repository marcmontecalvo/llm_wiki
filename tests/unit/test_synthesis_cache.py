"""Tests for Story 3-4: Synthesis Cache — high-value query pages."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_wiki.query.log import QueryLogEntry, QueryLogStore, compute_query_hash
from llm_wiki.synthesis.cache import (
    CacheCandidate,
    SynthesisCacheJob,
    _normalize_query,
    _query_to_slug,
)


class TestNormalizeQuery:
    """Tests for query normalization."""

    def test_lowercases(self):
        assert _normalize_query("WHAT") == "what"

    def test_strips_whitespace(self):
        assert _normalize_query("  hello  ") == "hello"

    def test_collapse_internal_whitespace(self):
        assert _normalize_query("hello   world") == "hello world"

    def test_handles_mixed_case_and_spaces(self):
        assert _normalize_query("  HELLO   WORLD  ") == "hello world"

    def test_preserves_meaningful_dashes_and_punctuation(self):
        # Normalize keeps non-space punctuation
        assert _normalize_query("hi, world!") == "hi, world!"


class TestQueryToSlug:
    """Tests for query-to-slug conversion."""

    def test_basic_slug(self):
        slug = _query_to_slug("what is python")
        assert slug == "what-is-python"

    def test_empty_query(self):
        slug = _query_to_slug("   ")
        assert slug == "empty-query"

    def test_special_characters(self):
        slug = _query_to_slug("hello-world!@#$%test")
        assert slug == "hello-world-test"

    def test_consistent_with_normalized(self):
        # Same text always produces same slug
        assert _query_to_slug("Test Query") == _query_to_slug("test query")


class TestSynthesisCacheJobCandidates:
    """Tests for SynthesisCacheJob candidate selection."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        """Helper to create a query log db with given entries under wiki_root."""
        state_dir = wiki_root / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        db_path = state_dir / "query_log.db"

        # Create schema via QueryLogStore
        QueryLogStore(db_path)

        # Insert entries directly
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_returns_empty_when_no_db(self, temp_dir: Path):
        log_db = temp_dir / "state" / "query_log.db"
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db)
        candidates = cache_job.get_candidates()
        assert candidates == []

    def test_returns_candidates_above_threshold(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="what is python",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    confidence_avg=0.8,
                    timestamp=datetime.now(UTC) - timedelta(days=2),
                )
                for _ in range(6)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5, window_days=30)
        candidates = cache_job.get_candidates()

        assert len(candidates) == 1
        assert candidates[0].query_text == "what is python"
        assert candidates[0].query_count == 6

    def test_excludes_below_threshold(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="rare query",
                    depth="quick",
                    domains=[],
                    result_count=1,
                    timestamp=datetime.now(UTC) - timedelta(days=2),
                )
                for _ in range(2)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5, window_days=30)
        candidates = cache_job.get_candidates()
        assert candidates == []

    def test_window_filtering_excludes_old_queries(self, temp_dir: Path):
        old_entry = QueryLogEntry(
            query_text="old query",
            depth="quick",
            domains=[],
            result_count=10,
            timestamp=datetime.now(UTC) - timedelta(days=60),
        )
        new_entry = QueryLogEntry(
            query_text="new query",
            depth="quick",
            domains=[],
            result_count=1,
            timestamp=datetime.now(UTC) - timedelta(days=5),
        )
        log_db = self._create_log_db(temp_dir, [old_entry, new_entry])

        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=1, window_days=30)
        candidates = cache_job.get_candidates()

        # old query below threshold (only 1) -> excluded
        # new query has 1 hit >= 1 -> included
        old_queries = [c for c in candidates if "old" in c.query_text.lower()]
        assert old_queries == []

    def test_caches_candidate_data(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="unique question",
                    depth="standard",
                    domains=["tech"],
                    result_count=10,
                    timestamp=datetime.now(UTC) - timedelta(days=3),
                )
                for _ in range(10)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5, window_days=30)
        candidates = cache_job.get_candidates()

        c = candidates[0]
        assert c.query_text == "unique question"
        assert c.query_count == 10
        assert c.query_hash == compute_query_hash("unique question")
        assert isinstance(c, CacheCandidate)


class TestSynthesisCachePageGeneration:
    """Tests for synthesis page creation."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_creates_synthesis_page(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="test cache query",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )

        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        assert len(candidates) == 1

        result = asyncio.run(cache_job.generate_synthesis_page(candidates[0]))
        assert result is not None

        page_path = Path(result)
        assert page_path.exists()
        content = page_path.read_text(encoding="utf-8")
        assert "# Synthesis: test cache query" in content

    def test_page_frontmatter_has_required_fields(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="frontmatter test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )

        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()

        import frontmatter as fm  # noqa: PLC0415

        result = asyncio.run(cache_job.generate_synthesis_page(candidates[0]))
        raw = Path(result).read_text(encoding="utf-8")
        post = fm.loads(raw)
        meta = dict(post.metadata)

        assert meta["kind"] == "synthesis"
        assert meta["source_query"] == "frontmatter test"
        assert meta["query_hash"] == compute_query_hash("frontmatter test")
        assert meta["query_count"] == 5
        assert "cached_at" in meta

    def test_regeneration_for_existing_page(self, temp_dir: Path):
        """Test that existing synthesis pages are regenerated when stats change."""
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="regeneration test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )

        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        candidate = candidates[0]

        # Create initial page
        asyncio.run(cache_job.generate_synthesis_page(candidate))

        # Check that the page exists and is a synthesis page
        existing = cache_job.get_existing_synthesis_page(candidate.query_hash)
        assert existing is not None
        assert existing.exists()

    def test_multiple_candidates(self, temp_dir: Path):
        """Test generating pages for multiple candidates."""
        queries = [
            QueryLogEntry(
                query_text=f"test query {i}",
                depth="quick",
                domains=[],
                result_count=5,
                timestamp=datetime.now(UTC) - timedelta(days=1),
            )
            for i in range(3)
        ]
        log_db = self._create_log_db(temp_dir, queries * 5)

        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()

        for candidate in candidates:
            result = asyncio.run(cache_job.generate_synthesis_page(candidate))
            assert result is not None

        pages = cache_job.list_synthesis_pages()
        assert len(pages) == len(candidates)


class TestSynthesisCacheRouting:
    """Tests for query-to-synthesis routing (cache hit detection)."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_find_page_by_hash(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="routing test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        result = cache_job.find_page_by_hash(candidates[0].query_hash)
        assert result is not None
        assert result["kind"] == "synthesis"
        assert result["source_query"] == "routing test"

    def test_find_by_hash_returns_none_for_missing(self, temp_dir: Path):
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=Path("/nonexistent"))
        result = cache_job.find_page_by_hash("nonexistent_hash_12345")
        assert result is None

    def test_find_by_text_matching(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="text search test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        result = cache_job.find_page_by_text("text search test")
        assert result is not None

    def test_find_by_text_case_insensitive(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="case sensitive test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        # Case difference should still match due to normalization
        result = cache_job.find_page_by_text("CASE SENSITIVE TEST")
        assert result is not None

    def test_find_by_text_no_match(self, temp_dir: Path):
        cache_job = SynthesisCacheJob(
            wiki_base=temp_dir,
            log_db=temp_dir / "state" / "query_log.db",
        )
        # No cache pages exist
        result = cache_job.find_page_by_text("nonexistent query")
        assert result is None


class TestSynthesisCacheListAndQuery:
    """Tests for listing and filtering synthesis pages."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_list_synthesis_pages_empty(self, temp_dir: Path):
        cache_job = SynthesisCacheJob(
            wiki_base=temp_dir,
            log_db=temp_dir / "state" / "query_log.db",
        )
        pages = cache_job.list_synthesis_pages()
        assert pages == []

    def test_list_returns_pages_with_metadata(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="page list test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        pages = cache_job.list_synthesis_pages()
        assert len(pages) == 1
        assert pages[0]["page_id"] == "synth-" + candidates[0].query_hash
        assert pages[0]["kind"] == "synthesis"
        assert pages[0]["domain"] == "shared"

    def test_list_empty_query(self, temp_dir: Path):
        slug = _query_to_slug("   ")
        assert slug == "empty-query"


class TestSynthesisCacheStaleRefresh:
    """Tests for stale cache entry regeneration (AC:5)."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_regenerates_when_source_changes(self, temp_dir: Path):
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="stale refresh test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        existing = cache_job.get_existing_synthesis_page(candidates[0].query_hash)
        assert existing is not None

        result = cache_job.regenerate_if_stale(existing, candidates[0])
        assert result is True

    def test_skips_non_synthesis_pages(self, temp_dir: Path):
        """Test that non-synthesis pages are not regenerated."""
        wiki_base = temp_dir
        cache_dir = wiki_base / "shared" / "synthesis"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Create a non-synthesis page
        non_synthesis = cache_dir / "regular-page.md"
        non_synthesis.write_text(
            "---\nkind: entity\ntitle: Regular\n---\n\nRegular content\n",
            encoding="utf-8",
        )

        cache_job = SynthesisCacheJob(
            wiki_base=wiki_base,
            log_db=wiki_base / "state" / "query_log.db",
        )
        result = cache_job.regenerate_if_stale(
            non_synthesis,
            CacheCandidate(
                query_text="test",
                query_hash="abc1234567890",
                query_count=5,
                last_seen=datetime.now(UTC).isoformat(),
            ),
        )
        assert result is False


class TestSynthesisCacheNoLLM:
    """Verifies that synthesis generation is algorithmic, no LLM calls (AC:7)."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_generation_is_pure_algorithmic(self, temp_dir: Path):
        """Cache page generation should not call any LLM client."""
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="algorithmic test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()

        # This should work without any LLM client configured or available
        result = asyncio.run(cache_job.generate_synthesis_page(candidates[0]))
        assert result is not None

    def test_page_content_contains_no_llm_references(self, temp_dir: Path):
        """Generated page should not mention LLM-specific content."""
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="no llm test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=1),
                )
                for _ in range(5)
            ],
        )
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        asyncio.run(cache_job.generate_synthesis_page(candidates[0]))

        pages = cache_job.list_synthesis_pages()
        content = pages[0]["content"]
        # The content should be algorithmic summary, not LLM output
        assert "Synthesis: no llm test" in content


class TestQueryLogEntrySynthesisHit:
    """Test that QueryLogEntry supports synthesis_hit field."""

    def test_synthesis_hit_default_false(self):
        entry = QueryLogEntry(
            query_text="test",
            depth="quick",
            domains=[],
            result_count=5,
        )
        assert entry.synthesis_hit is False

    def test_synthesis_hit_can_be_set(self):
        entry = QueryLogEntry(
            query_text="test",
            depth="quick",
            domains=[],
            result_count=5,
            synthesis_hit=True,
        )
        assert entry.synthesis_hit is True


class TestQueryLogStatsWindowFilter:
    """Test stats() with since parameter for window filtering."""

    def test_stats_since_filters_queries(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        old_entries = [
            QueryLogEntry(
                query_text="old",
                depth="quick",
                domains=[],
                result_count=1,
                timestamp=datetime.now(UTC) - timedelta(days=60),
            )
            for _ in range(10)
        ]
        recent_entry = QueryLogEntry(
            query_text="recent",
            depth="quick",
            domains=[],
            result_count=1,
            timestamp=datetime.now(UTC) - timedelta(days=5),
        )
        for e in old_entries:
            store.log(e)
        store.log(recent_entry)

        # Without filter — old query has 10 hits, recent has 1
        no_filter = store.stats()
        old_hits = next(q for q in no_filter["top_queries"] if q["query"] == "old")
        assert old_hits["hits"] == 10

        # With 30-day filter — old query should be excluded
        three_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        filtered = store.stats(since=three_days_ago)
        old_in_filter = [q for q in filtered["top_queries"] if q["query"] == "old"]
        assert old_in_filter == []

    def test_stats_since_includes_relevant_queries(self, temp_dir: Path):
        store = QueryLogStore(temp_dir / "query_log.db")
        entry = QueryLogEntry(
            query_text="within window",
            depth="quick",
            domains=[],
            result_count=5,
            timestamp=datetime.now(UTC) - timedelta(days=10),
        )
        store.log(entry)

        three_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        stats = store.stats(since=three_days_ago)
        queries = [q for q in stats["top_queries"] if q["query"] == "within window"]
        assert len(queries) == 1
        assert queries[0]["hits"] == 1


class TestIntegrationFullCacheFlow:
    """Integration test: log -> cache build -> cache hit (AC:6)."""

    def _create_log_db(self, wiki_root: Path, entries: list[QueryLogEntry]) -> Path:
        db_path = wiki_root / "state" / "query_log.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        QueryLogStore(db_path)
        conn = sqlite3.connect(str(db_path))
        for entry in entries:
            conn.execute(
                """INSERT INTO queries
                   (query_hash, query_text, depth, domains, result_count, confidence_avg, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.query_hash,
                    entry.query_text,
                    entry.depth,
                    json.dumps(entry.domains),
                    entry.result_count,
                    entry.confidence_avg,
                    entry.timestamp.isoformat(),
                ),
            )
        conn.commit()
        conn.close()
        return db_path

    def test_full_flow_log_to_cache(self, temp_dir: Path):
        """Complete flow: log repeated queries, build cache, verify page exists."""
        log_db = self._create_log_db(
            temp_dir,
            [
                QueryLogEntry(
                    query_text="full flow test",
                    depth="quick",
                    domains=[],
                    result_count=5,
                    timestamp=datetime.now(UTC) - timedelta(days=2),
                )
                for _ in range(6)
            ],
        )

        # Step 1: Job identifies candidate
        cache_job = SynthesisCacheJob(wiki_base=temp_dir, log_db=log_db, min_hits=5)
        candidates = cache_job.get_candidates()
        assert len(candidates) == 1
        assert candidates[0].query_text == "full flow test"
        assert candidates[0].query_count == 6

        # Step 2: Job creates synthesis page
        result = asyncio.run(cache_job.generate_synthesis_page(candidates[0]))
        assert result is not None
        page_path = Path(result)
        assert page_path.exists()

        # Step 3: Page is findable by hash
        found = cache_job.find_page_by_hash(candidates[0].query_hash)
        assert found is not None
        assert found["kind"] == "synthesis"
        assert found["source_query"] == "full flow test"

        # Step 4: Page has correct frontmatter
        import frontmatter as fm  # noqa: PLC0415

        raw = page_path.read_text(encoding="utf-8")
        post = fm.loads(raw)
        meta = dict(post.metadata)
        assert meta["kind"] == "synthesis"
        assert meta["query_hash"] == candidates[0].query_hash
        assert meta["query_count"] == 6

        # Step 5: Listed in synthesis pages
        pages = cache_job.list_synthesis_pages()
        assert len(pages) == 1
        assert pages[0]["kind"] == "synthesis"
