"""Tests for backlink index."""

from pathlib import Path

import pytest

from llm_wiki.index.backlinks import BacklinkIndex


class TestBacklinkIndex:
    """Tests for BacklinkIndex."""

    @pytest.fixture
    def index(self, temp_dir: Path) -> BacklinkIndex:
        """Create backlink index in temp directory."""
        index_dir = temp_dir / "index"
        return BacklinkIndex(index_dir=index_dir)

    def test_extract_links(self, index: BacklinkIndex):
        """Test link extraction from content."""
        content = """
        This page mentions [[page1]] and [[page2]].
        It also has a duplicate link to [[page1]].
        """

        links = index._extract_links(content)

        assert "page1" in links
        assert "page2" in links

    def test_extract_links_handles_nested_brackets(self, index: BacklinkIndex):
        """Test that nested brackets are handled correctly."""
        content = "Link to [[page-id-1]] but not [broken]."

        links = index._extract_links(content)

        assert links == ["page-id-1"]

    def test_extract_links_empty_content(self, index: BacklinkIndex):
        """Test extracting links from empty content."""
        content = "No links here."

        links = index._extract_links(content)

        assert links == []

    def test_add_page_links_creates_entry(self, index: BacklinkIndex):
        """Test adding links for a new page."""
        content = "Links to [[target1]] and [[target2]]."

        forward = index.add_page_links("page1", content)

        assert set(forward) == {"target1", "target2"}
        assert "page1" in index.index
        assert index.index["page1"]["forward_links"] == {"target1", "target2"}

    def test_add_page_links_creates_backlinks(self, index: BacklinkIndex):
        """Test that adding forward links creates backlinks in targets."""
        index.add_page_links("page1", "Links to [[target1]] and [[target2]].")

        # Targets should have page1 in their backlinks
        assert "page1" in index.index["target1"]["backlinks"]
        assert "page1" in index.index["target2"]["backlinks"]

    def test_add_page_links_updates_existing(self, index: BacklinkIndex):
        """Test updating links for existing page."""
        index.add_page_links("page1", "Links to [[old1]].")
        assert "old1" in index.index["page1"]["forward_links"]

        # Update with new links
        index.add_page_links("page1", "Links to [[new1]] and [[new2]].")

        # Old link should be gone
        assert "old1" not in index.index["page1"]["forward_links"]
        # New links should be present
        assert "new1" in index.index["page1"]["forward_links"]
        assert "new2" in index.index["page1"]["forward_links"]

        # Old target should not have page1 as backlink
        assert "page1" not in index.index["old1"]["backlinks"]
        # New targets should have page1 as backlink
        assert "page1" in index.index["new1"]["backlinks"]

    def test_remove_page(self, index: BacklinkIndex):
        """Test removing a page from index."""
        index.add_page_links("page1", "Links to [[target1]].")
        index.add_page_links("page2", "Links to [[page1]].")

        index.remove_page("page1")

        # page1 should be gone
        assert "page1" not in index.index
        # page2 should have page1 in broken links
        assert "page1" in index.index["page2"]["broken_links"]
        assert "page1" not in index.index["page2"]["forward_links"]

    def test_remove_nonexistent_page(self, index: BacklinkIndex):
        """Test removing a page that doesn't exist."""
        # Should not raise error
        index.remove_page("nonexistent")

    def test_rename_page(self, index: BacklinkIndex):
        """Test renaming a page."""
        index.add_page_links("old-id", "Links to [[target1]].")
        index.add_page_links("page2", "Links to [[old-id]].")

        index.rename_page("old-id", "new-id")

        # Old ID should be gone
        assert "old-id" not in index.index
        # New ID should exist
        assert "new-id" in index.index
        # Forward links should be preserved
        assert "target1" in index.index["new-id"]["forward_links"]
        # page2 should link to new-id
        assert "new-id" in index.index["page2"]["forward_links"]
        assert "old-id" not in index.index["page2"]["forward_links"]

    def test_rename_nonexistent_page(self, index: BacklinkIndex):
        """Test renaming a page that doesn't exist."""
        # Should log warning but not crash
        index.rename_page("nonexistent", "new-id")

    def test_get_backlinks(self, index: BacklinkIndex):
        """Test getting backlinks for a page."""
        index.add_page_links("page1", "Links to [[target1]].")
        index.add_page_links("page2", "Links to [[target1]].")
        index.add_page_links("page3", "Links to [[target2]].")

        backlinks = index.get_backlinks("target1")

        assert set(backlinks) == {"page1", "page2"}

    def test_get_backlinks_none(self, index: BacklinkIndex):
        """Test getting backlinks when there are none."""
        backlinks = index.get_backlinks("orphan")

        assert backlinks == []

    def test_get_forward_links(self, index: BacklinkIndex):
        """Test getting forward links for a page."""
        index.add_page_links("page1", "Links to [[target1]] and [[target2]].")

        forward = index.get_forward_links("page1")

        assert set(forward) == {"target1", "target2"}

    def test_get_broken_links(self, index: BacklinkIndex):
        """Test getting broken links for a page."""
        index.add_page_links("page1", "Links to [[exists]] and [[missing]].")

        # Mark "missing" as broken
        index.index["page1"]["broken_links"].add("missing")

        broken = index.get_broken_links("page1")

        assert "missing" in broken

    def test_update_broken_links(self, index: BacklinkIndex):
        """Test broken link detection."""
        index.add_page_links("page1", "Links to [[exists]] and [[missing]].")
        index.add_page_links("page2", "Links to [[exists]].")

        all_pages = {"page1", "page2", "exists"}
        stats = index.update_broken_links(all_pages)

        # page1 should have "missing" as broken
        assert "missing" in index.index["page1"]["broken_links"]
        # page2 should have no broken links
        assert len(index.index["page2"]["broken_links"]) == 0

        assert stats["total_broken_links"] == 1
        assert stats["pages_with_broken_links"] == 1

    def test_update_broken_links_clears_fixed(self, index: BacklinkIndex):
        """Test that broken links are cleared when target becomes valid."""
        index.add_page_links("page1", "Links to [[target1]].")
        index.index["page1"]["broken_links"].add("target1")

        # Now add target1 as a valid page
        all_pages = {"page1", "target1"}
        index.update_broken_links(all_pages)

        # target1 should no longer be broken
        assert len(index.index["page1"]["broken_links"]) == 0

    def test_get_orphan_pages(self, index: BacklinkIndex):
        """Test finding orphan pages."""
        index.add_page_links("page1", "Links to [[target1]].")
        index.add_page_links("page2", "Links to [[target1]].")
        # page3 and orphan have no backlinks

        all_pages = {"page1", "page2", "target1", "page3", "orphan"}
        orphans = index.get_orphan_pages(all_pages)

        # page3 and orphan have no incoming links
        assert "page3" in orphans
        assert "orphan" in orphans
        # page1 and page2 have no incoming links (they're orphans)
        assert "page1" in orphans
        assert "page2" in orphans
        # target1 has backlinks from page1 and page2, so it's not an orphan
        assert "target1" not in orphans

    def test_get_link_stats(self, index: BacklinkIndex):
        """Test getting link statistics."""
        index.add_page_links("page1", "Links to [[target1]] and [[target2]].")
        index.add_page_links("page2", "Links to [[target1]].")
        index.index["page1"]["broken_links"].add("missing")

        stats = index.get_link_stats()

        assert stats["total_pages"] == 4  # page1, page2, target1, target2
        assert stats["total_forward_links"] == 3  # page1->target1/2, page2->target1
        assert stats["total_broken_links"] == 1

    def test_save_and_load(self, index: BacklinkIndex, temp_dir: Path):
        """Test saving and loading index."""
        index.add_page_links("page1", "Links to [[target1]] and [[target2]].")
        index.add_page_links("page2", "Links to [[target1]].")
        index.index["page1"]["broken_links"].add("missing")

        # Save
        index.save()

        # Create new index and load
        index2 = BacklinkIndex(index_dir=temp_dir / "index")
        index2.load()

        # Verify data was loaded
        assert len(index2.index) == 4
        assert index2.index["page1"]["forward_links"] == {"target1", "target2"}
        assert "page1" in index2.index["target1"]["backlinks"]
        assert index2.index["page1"]["broken_links"] == {"missing"}

    def test_load_nonexistent_index(self, index: BacklinkIndex):
        """Test loading when no index exists."""
        # Should not raise error
        index.load()
        assert len(index.index) == 0

    def test_rebuild_from_pages(self, index: BacklinkIndex, temp_dir: Path):
        """Test rebuilding index from wiki pages."""
        # Create wiki structure
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create test pages with links
        page1 = domain_dir / "page1.md"
        page1.write_text(
            """---
id: page1
title: Page One
---

Links to [[page2]] and [[page3]].
"""
        )

        page2 = domain_dir / "page2.md"
        page2.write_text(
            """---
id: page2
title: Page Two
---

Links to [[page1]].
"""
        )

        page3 = domain_dir / "page3.md"
        page3.write_text(
            """---
id: page3
title: Page Three
---

No links here.
"""
        )

        # Rebuild
        count = index.rebuild_from_pages(wiki_base)

        assert count == 3
        assert "page1" in index.index
        assert "page2" in index.index
        assert "page3" in index.index

        # Check forward links
        assert "page2" in index.index["page1"]["forward_links"]
        assert "page3" in index.index["page1"]["forward_links"]
        assert "page1" in index.index["page2"]["forward_links"]

        # Check backlinks
        assert "page1" in index.index["page2"]["backlinks"]
        assert "page1" in index.index["page3"]["backlinks"]
        assert "page2" in index.index["page1"]["backlinks"]

    def test_rebuild_handles_missing_domains(self, index: BacklinkIndex, temp_dir: Path):
        """Test rebuild when domains directory doesn't exist."""
        wiki_base = temp_dir / "wiki"

        count = index.rebuild_from_pages(wiki_base)

        assert count == 0

    def test_rebuild_handles_errors(self, index: BacklinkIndex, temp_dir: Path):
        """Test rebuild handles invalid files gracefully."""
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create invalid page (bad YAML)
        invalid_page = domain_dir / "invalid.md"
        invalid_page.write_text("---\ninvalid: yaml: syntax:\n---\nContent")

        # Valid page
        valid_page = domain_dir / "valid.md"
        valid_page.write_text("---\nid: valid\ntitle: Valid\n---\nContent")

        # Should not crash
        count = index.rebuild_from_pages(wiki_base)

        # Only valid page should be indexed
        assert count == 1
        assert "valid" in index.index

    def test_rebuild_clears_existing(self, index: BacklinkIndex, temp_dir: Path):
        """Test rebuild clears existing index data."""
        # Add initial data
        index.add_page_links("old-page", "Links to [[target]].")

        # Create wiki with new data
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        new_page = domain_dir / "new-page.md"
        new_page.write_text("---\nid: new-page\ntitle: New\n---\nContent")

        # Rebuild
        index.rebuild_from_pages(wiki_base)

        # Old data should be gone
        assert "old-page" not in index.index
        assert "new-page" in index.index

    def test_bidirectional_linking_consistency(self, index: BacklinkIndex):
        """Test that forward and backlinks are always consistent."""
        # Add some pages with links
        index.add_page_links("page1", "Links to [[page2]].")
        index.add_page_links("page2", "Links to [[page3]].")
        index.add_page_links("page3", "Links to [[page1]].")

        # Check consistency
        for page_id in index.index:
            for target in index.index[page_id]["forward_links"]:
                # Each forward link should have a corresponding backlink
                assert page_id in index.index[target]["backlinks"]

            for source in index.index[page_id]["backlinks"]:
                # Each backlink should have a corresponding forward link
                assert page_id in index.index[source]["forward_links"]

    def test_deduplication_of_links(self, index: BacklinkIndex):
        """Test that duplicate links are deduplicated."""
        content = "Links to [[page2]], [[page2]], and [[page2]]."

        forward = index.add_page_links("page1", content)

        # Should have only one copy of page2
        assert forward == ["page2"]
        assert index.index["page1"]["forward_links"] == {"page2"}

    def test_complex_linking_scenario(self, index: BacklinkIndex):
        """Test a complex linking scenario with multiple operations."""
        # Create a link network
        index.add_page_links("page1", "Links to [[page2]] and [[page3]].")
        index.add_page_links("page2", "Links to [[page3]] and [[page4]].")
        index.add_page_links("page3", "Links to [[page1]].")

        # Verify initial state
        assert index.get_backlinks("page1") == ["page3"]
        assert set(index.get_backlinks("page2")) == {"page1"}
        assert set(index.get_backlinks("page3")) == {"page1", "page2"}
        assert index.get_backlinks("page4") == ["page2"]

        # Update page1 to link differently
        index.add_page_links("page1", "Links to [[page2]] and [[page4]].")

        # Verify updated state
        assert index.get_backlinks("page1") == ["page3"]  # Still has page3
        assert set(index.get_backlinks("page2")) == {"page1"}
        assert index.get_backlinks("page3") == ["page2"]  # Lost page1
        assert set(index.get_backlinks("page4")) == {"page1", "page2"}

        # Remove page2
        index.remove_page("page2")

        # Verify cleanup
        assert "page2" not in index.index
        # page1 linked to page2, so now it's a broken link
        assert "page2" in index.index["page1"]["broken_links"]
        # page4 didn't link to page2, it just lost a backlink
        assert "page2" not in index.index["page4"]["broken_links"]
        assert "page2" not in index.index["page4"]["backlinks"]
