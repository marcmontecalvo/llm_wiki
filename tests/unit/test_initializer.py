"""Unit tests for WikiInitializer and _maybe_init_wiki_root."""

from pathlib import Path

from llm_wiki.initializer import WikiInitializer, _maybe_init_wiki_root


def test_initialize_creates_all_subdirs(temp_dir: Path) -> None:
    WikiInitializer.initialize(temp_dir)
    assert (temp_dir / "domains").is_dir()
    assert (temp_dir / "inbox" / "new").is_dir()
    assert (temp_dir / "inbox" / "processing").is_dir()
    assert (temp_dir / "exports").is_dir()
    assert (temp_dir / "state").is_dir()


def test_initialize_is_idempotent(temp_dir: Path) -> None:
    WikiInitializer.initialize(temp_dir)
    # Second call should not raise
    WikiInitializer.initialize(temp_dir)
    assert (temp_dir / "domains").is_dir()


def test_initialize_domain_creates_domain_subdirs(temp_dir: Path) -> None:
    WikiInitializer.initialize_domain(temp_dir, "test-domain")
    assert (temp_dir / "domains" / "test-domain" / "pages").is_dir()
    assert (temp_dir / "domains" / "test-domain" / "queue").is_dir()


def test_maybe_init_creates_when_missing_domains(temp_dir: Path) -> None:
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "domains").is_dir()


def test_maybe_init_skips_if_domains_exist(temp_dir: Path) -> None:
    (temp_dir / "domains").mkdir()
    # Should be no-op — no exception raised
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "domains").is_dir()


def test_initialize_all_domains(temp_dir: Path) -> None:
    WikiInitializer.initialize_all_domains(temp_dir, ["domain-a", "domain-b"])
    assert (temp_dir / "domains" / "domain-a" / "pages").is_dir()
    assert (temp_dir / "domains" / "domain-b" / "pages").is_dir()
