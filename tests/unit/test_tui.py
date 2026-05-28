"""Tests for TUI components."""

from unittest.mock import patch

from llm_wiki.tui.api import WikiAPI
from llm_wiki.tui.offline import OfflineReader


class TestOfflineReader:
    def test_scans_domain_pages(self, tmp_path):
        # Setup wiki structure
        domain_dir = tmp_path / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)
        md_file = domain_dir / "test-page.md"
        md_file.write_text("---\ntitle: Test\n---\nHello world")
        reader = OfflineReader(tmp_path)
        pages = reader.list_pages()
        assert len(pages) == 1
        assert pages[0].page_id == "test-page"
        assert pages[0].title == "Test"

    def test_lists_domains(self, tmp_path):
        docs_dir = tmp_path / "domains"
        docs_dir.mkdir(parents=True)
        (docs_dir / "a" / "pages").mkdir(parents=True)
        (docs_dir / "a" / "pages" / "p1.md").write_text("---\ntitle: A\n---\n")
        (docs_dir / "b" / "pages").mkdir(parents=True)
        reader = OfflineReader(tmp_path)
        domains = reader.list_domains()
        assert len(domains) == 2
        assert domains[0]["page_count"] == 1
        assert domains[1]["page_count"] == 0

    def test_reads_page(self, tmp_path):
        domain_dir = tmp_path / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)
        md_file = domain_dir / "test-page.md"
        md_file.write_text("---\ntitle: Test Article\n---\nHello world")
        reader = OfflineReader(tmp_path)
        page = reader.read_page("test-page")
        assert page is not None
        assert page.title == "Test Article"
        assert page.content == "Hello world"

    def test_reads_shared_page(self, tmp_path):
        shared = tmp_path / "shared"
        shared.mkdir(parents=True)
        shared_file = shared / "shared-page.md"
        shared_file.write_text("---\ntitle: Shared\n---\nShared content")
        reader = OfflineReader(tmp_path)
        page = reader.read_page("shared-page")
        assert page is not None
        assert page.domain == "shared"

    def test_reads_nothing(self, tmp_path):
        reader = OfflineReader(tmp_path)
        assert reader.read_page("missing") is None

    def test_filters_by_domain(self, tmp_path):
        (tmp_path / "domains" / "a" / "pages").mkdir(parents=True)
        (tmp_path / "domains" / "a" / "pages" / "1.md").write_text(
            "---\ntitle: One\ndomain: a\n---\n"
        )
        (tmp_path / "domains" / "b" / "pages").mkdir(parents=True)
        (tmp_path / "domains" / "b" / "pages" / "2.md").write_text(
            "---\ntitle: Two\ndomain: b\n---\n"
        )
        reader = OfflineReader(tmp_path)
        pages = reader.list_pages(domain="a")
        assert len(pages) == 1
        assert pages[0].domain == "a"


class TestWikiAPI:
    def test_init_sets_auth(self):
        with patch("requests.Session") as mock_session:
            mock_session.return_value.auth = None
            api = WikiAPI("http://localhost:8000", "user", "pass")
            assert mock_session.return_value.auth == ("user", "pass")
            assert api.base_url == "http://localhost:8000"


class TestCredentials:
    """Test credential loading from .env and credentials file."""

    def test_app_context_defaults(self):
        import os

        from llm_wiki.tui.app import AppContext

        # Ensure env is clean — tests may set these (e.g. integration suite)
        env_before = {
            "WIKI_UI_USER": os.environ.pop("WIKI_UI_USER", None),
            "WIKI_UI_PASSWORD": os.environ.pop("WIKI_UI_PASSWORD", None),
        }
        try:
            ctx = AppContext()
            assert ctx.username == "admin"
            assert ctx.password == ""
        finally:
            for k, v in env_before.items():
                if v is not None:
                    os.environ[k] = v
