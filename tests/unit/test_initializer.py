"""Unit tests for WikiInitializer and _maybe_init_wiki_root."""

from pathlib import Path

from llm_wiki.initializer import WikiInitializer, _maybe_init_wiki_root


def test_initialize_creates_all_subdirs(temp_dir: Path) -> None:
    """AC1: All required directories are created under wiki_root."""
    WikiInitializer.initialize(temp_dir)
    ws = temp_dir  # wiki_root IS the root in current architecture

    # Domain root
    assert (ws / "domains").is_dir()

    # Inbox subdirs including staging (needed by Story 1.15)
    assert (ws / "inbox" / "new").is_dir()
    assert (ws / "inbox" / "processing").is_dir()
    assert (ws / "inbox" / "done").is_dir()
    assert (ws / "inbox" / "failed").is_dir()
    assert (ws / "inbox" / "staging").is_dir()

    # Shared
    assert (ws / "shared" / "concepts").is_dir()
    assert (ws / "shared" / "entities").is_dir()
    assert (ws / "shared" / "synthesis").is_dir()

    # Index
    assert (ws / "index").is_dir()

    # Review queue
    assert (ws / "review_queue" / "pending").is_dir()
    assert (ws / "review_queue" / "approved").is_dir()
    assert (ws / "review_queue" / "rejected").is_dir()
    assert (ws / "review_queue" / "deferred").is_dir()

    # State and logs
    assert (ws / "state").is_dir()
    assert (ws / "logs").is_dir()

    # Export and reports
    assert (ws / "exports").is_dir()
    assert (ws / "reports").is_dir()


def test_initialize_creates_changelog(temp_dir: Path) -> None:
    """AC1: Empty changelog.jsonl is created in logs/."""
    WikiInitializer.initialize(temp_dir)
    changelog = temp_dir / "logs" / "changelog.jsonl"
    assert changelog.exists()
    assert changelog.stat().st_size == 0


def test_initialize_is_idempotent(temp_dir: Path) -> None:
    """AC2: Calling initialize() twice is safe — no errors, no corruption."""
    WikiInitializer.initialize(temp_dir)
    WikiInitializer.initialize(temp_dir)  # second call must not raise
    # Verify no data was corrupted
    assert (temp_dir / "domains").is_dir()


def test_maybe_init_creates_on_fresh_volume(temp_dir: Path) -> None:
    """AC2: Sentinel-based check triggers init when domains/ is missing."""
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "domains").is_dir()


def test_maybe_init_skips_if_domains_exist(temp_dir: Path) -> None:
    """AC2: Sentinel-based check skips when domains/ already exists."""
    (temp_dir / "domains").mkdir(parents=True)
    # Should be no-op — no exception raised
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "domains").is_dir()


def test_maybe_init_creates_all_dir_structure(temp_dir: Path) -> None:
    """AC2: When sentinel is missing, full structure is created."""
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "inbox" / "new").is_dir()
    assert (temp_dir / "index").is_dir()
    assert (temp_dir / "review_queue" / "pending").is_dir()


def test_initialize_all_domains(temp_dir: Path) -> None:
    WikiInitializer.initialize_all_domains(temp_dir, ["domain-a", "domain-b"])
    assert (temp_dir / "domains" / "domain-a" / "pages").is_dir()
    assert (temp_dir / "domains" / "domain-b" / "pages").is_dir()


def test_initialize_domain_creates_domain_subdirs(temp_dir: Path) -> None:
    WikiInitializer.initialize_domain(temp_dir, "test-domain")
    assert (temp_dir / "domains" / "test-domain" / "pages").is_dir()
    assert (temp_dir / "domains" / "test-domain" / "queue").is_dir()
