"""Unit tests for the changelog module."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from llm_wiki.changelog.log import ChangeLog, _fmt_val, _format_field_change
from llm_wiki.changelog.models import ChangeLogEntry, FieldChange, diff_metadata

# ---------------------------------------------------------------------------
# FieldChange
# ---------------------------------------------------------------------------


class TestFieldChange:
    def test_to_dict_round_trip(self):
        fc = FieldChange(
            field="tags", old_value=["a"], new_value=["a", "b"], change_type="modified"
        )
        d = fc.to_dict()
        restored = FieldChange.from_dict(d)
        assert restored.field == "tags"
        assert restored.old_value == ["a"]
        assert restored.new_value == ["a", "b"]
        assert restored.change_type == "modified"

    def test_from_dict_handles_missing_old_value(self):
        d = {"field": "title", "new_value": "Hello", "change_type": "added"}
        fc = FieldChange.from_dict(d)
        assert fc.old_value is None
        assert fc.new_value == "Hello"

    def test_from_dict_handles_missing_new_value(self):
        d = {"field": "title", "old_value": "Hello", "change_type": "removed"}
        fc = FieldChange.from_dict(d)
        assert fc.new_value is None
        assert fc.old_value == "Hello"


# ---------------------------------------------------------------------------
# ChangeLogEntry
# ---------------------------------------------------------------------------


class TestChangeLogEntry:
    def test_create_generates_id_and_timestamp(self):
        entry = ChangeLogEntry.create(page_id="p1", change_type="created", actor="test")
        assert len(entry.id) == 16
        assert "T" in entry.timestamp
        assert entry.page_id == "p1"
        assert entry.change_type == "created"
        assert entry.actor == "test"

    def test_create_unique_ids(self):
        e1 = ChangeLogEntry.create(page_id="p1", change_type="created", actor="test")
        e2 = ChangeLogEntry.create(page_id="p1", change_type="created", actor="test")
        assert e1.id != e2.id

    def test_create_with_changes_and_reason(self):
        fc = FieldChange("title", "old", "new", "modified")
        entry = ChangeLogEntry.create(
            page_id="p1",
            change_type="updated",
            actor="test",
            changes=[fc],
            reason="user request",
            parent_change_id="abc123",
        )
        assert len(entry.changes) == 1
        assert entry.reason == "user request"
        assert entry.parent_change_id == "abc123"

    def test_to_dict_round_trip(self):
        fc = FieldChange("title", "old", "new", "modified")
        entry = ChangeLogEntry.create(
            page_id="page-1",
            change_type="updated",
            actor="extractor",
            changes=[fc],
            reason="extraction run",
        )
        d = entry.to_dict()
        restored = ChangeLogEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.page_id == entry.page_id
        assert restored.change_type == entry.change_type
        assert restored.actor == entry.actor
        assert restored.reason == entry.reason
        assert len(restored.changes) == 1
        assert restored.changes[0].field == "title"

    def test_default_values(self):
        entry = ChangeLogEntry.create(page_id="p", change_type="created", actor="a")
        assert entry.changes == []
        assert entry.reason is None
        assert entry.parent_change_id is None


# ---------------------------------------------------------------------------
# diff_metadata
# ---------------------------------------------------------------------------


class TestDiffMetadata:
    def test_added_field(self):
        changes = diff_metadata({}, {"title": "Hello"})
        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert changes[0].field == "title"
        assert changes[0].new_value == "Hello"
        assert changes[0].old_value is None

    def test_removed_field(self):
        changes = diff_metadata({"title": "Hello"}, {})
        assert len(changes) == 1
        assert changes[0].change_type == "removed"
        assert changes[0].old_value == "Hello"
        assert changes[0].new_value is None

    def test_modified_field(self):
        changes = diff_metadata({"title": "Old"}, {"title": "New"})
        assert len(changes) == 1
        assert changes[0].change_type == "modified"
        assert changes[0].old_value == "Old"
        assert changes[0].new_value == "New"

    def test_unchanged_field_not_reported(self):
        changes = diff_metadata({"title": "Same"}, {"title": "Same"})
        assert changes == []

    def test_multiple_changes(self):
        old = {"title": "A", "tags": ["x"], "kind": "note"}
        new = {"title": "B", "tags": ["x", "y"]}
        changes = diff_metadata(old, new)
        fields = {c.field for c in changes}
        assert "title" in fields
        assert "tags" in fields
        assert "kind" in fields  # removed

    def test_tracked_fields_filter(self):
        old = {"title": "A", "summary": "old"}
        new = {"title": "B", "summary": "new", "tags": ["x"]}
        # Only track title
        changes = diff_metadata(old, new, tracked_fields=["title"])
        assert len(changes) == 1
        assert changes[0].field == "title"

    def test_list_values_compared_correctly(self):
        old = {"tags": ["a", "b"]}
        new = {"tags": ["a", "b", "c"]}
        changes = diff_metadata(old, new)
        assert len(changes) == 1
        assert changes[0].change_type == "modified"

    def test_none_old_is_added(self):
        # old has key but value is None — should still be treated as absent
        changes = diff_metadata({"title": None}, {"title": "Hello"})
        assert len(changes) == 1
        assert changes[0].change_type == "added"


# ---------------------------------------------------------------------------
# ChangeLog — persistence
# ---------------------------------------------------------------------------


class TestChangeLogPersistence:
    def test_ensure_dirs_creates_directories(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.ensure_dirs()
        assert (tmp_path / "changelog").exists()
        assert (tmp_path / "changelog" / "pages").exists()

    def test_record_creates_page_file(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.record("page-1", "created", "test-actor")
        page_file = tmp_path / "changelog" / "pages" / "page-1.json"
        assert page_file.exists()

    def test_record_creates_index_file(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.record("page-1", "created", "test-actor")
        assert (tmp_path / "changelog" / "index.json").exists()

    def test_save_load_round_trip(self, tmp_path):
        cl1 = ChangeLog(changelog_dir=tmp_path / "changelog")
        entry = cl1.record("page-1", "created", "actor-a")

        # Load fresh instance
        cl2 = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl2.load_index()
        loaded = cl2.get_entry(entry.id)
        assert loaded is not None
        assert loaded.id == entry.id
        assert loaded.page_id == "page-1"
        assert loaded.change_type == "created"

    def test_page_file_contains_valid_json(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.record("p1", "created", "actor")
        raw = json.loads((tmp_path / "changelog" / "pages" / "p1.json").read_text())
        assert isinstance(raw, list)
        assert len(raw) == 1
        assert raw[0]["page_id"] == "p1"


# ---------------------------------------------------------------------------
# ChangeLog — record
# ---------------------------------------------------------------------------


class TestChangeLogRecord:
    def test_first_record_has_no_parent(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        entry = cl.record("p1", "created", "actor")
        assert entry.parent_change_id is None

    def test_second_record_links_to_first(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        e1 = cl.record("p1", "created", "actor")
        e2 = cl.record("p1", "updated", "actor")
        assert e2.parent_change_id == e1.id

    def test_different_pages_independent_chains(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        e2 = cl.record("p2", "created", "actor")
        assert e2.parent_change_id is None

    def test_record_with_field_changes(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        fc = FieldChange("title", None, "Hello", "added")
        entry = cl.record("p1", "created", "actor", changes=[fc])
        assert len(entry.changes) == 1
        assert entry.changes[0].field == "title"

    def test_max_entries_per_page_prunes_oldest(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl", max_entries_per_page=3)
        for i in range(5):
            cl.record("p1", "updated", f"actor-{i}")
        history = cl.get_page_history("p1", limit=0)
        assert len(history) == 3


# ---------------------------------------------------------------------------
# ChangeLog — get_page_history
# ---------------------------------------------------------------------------


class TestGetPageHistory:
    def test_returns_empty_for_unknown_page(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        assert cl.get_page_history("nonexistent") == []

    def test_returns_newest_first(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        e1 = cl.record("p1", "created", "actor")
        e2 = cl.record("p1", "updated", "actor")
        history = cl.get_page_history("p1")
        assert history[0].id == e2.id
        assert history[1].id == e1.id

    def test_limit_applied(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        for _ in range(5):
            cl.record("p1", "updated", "actor")
        history = cl.get_page_history("p1", limit=2)
        assert len(history) == 2

    def test_limit_zero_returns_all(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        for _ in range(5):
            cl.record("p1", "updated", "actor")
        history = cl.get_page_history("p1", limit=0)
        assert len(history) == 5


# ---------------------------------------------------------------------------
# ChangeLog — get_recent_changes
# ---------------------------------------------------------------------------


class TestGetRecentChanges:
    def test_returns_all_without_since(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        cl.record("p2", "created", "actor")
        results = cl.get_recent_changes()
        assert len(results) == 2

    def test_since_filter_excludes_older(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        # Use a future cutoff — should exclude all entries
        future = datetime.now(UTC) + timedelta(hours=1)
        results = cl.get_recent_changes(since=future)
        assert results == []

    def test_since_filter_includes_newer(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        past = datetime.now(UTC) - timedelta(hours=1)
        cl.record("p1", "created", "actor")
        results = cl.get_recent_changes(since=past)
        assert len(results) == 1

    def test_limit_applied(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        for i in range(5):
            cl.record(f"p{i}", "created", "actor")
        results = cl.get_recent_changes(limit=3)
        assert len(results) == 3

    def test_newest_first(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        cl.record("p2", "created", "actor")
        results = cl.get_recent_changes()
        # Most recent should come first
        assert results[0].timestamp >= results[1].timestamp


# ---------------------------------------------------------------------------
# ChangeLog — get_changes_by_actor
# ---------------------------------------------------------------------------


class TestGetChangesByActor:
    def test_filters_by_actor(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "alice")
        cl.record("p2", "created", "bob")
        cl.record("p3", "created", "alice")
        results = cl.get_changes_by_actor("alice")
        assert all(e.actor == "alice" for e in results)
        assert len(results) == 2

    def test_returns_empty_for_unknown_actor(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "alice")
        assert cl.get_changes_by_actor("unknown") == []

    def test_limit_applied(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        for i in range(5):
            cl.record(f"p{i}", "created", "alice")
        results = cl.get_changes_by_actor("alice", limit=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# ChangeLog — get_entry
# ---------------------------------------------------------------------------


class TestGetEntry:
    def test_returns_none_for_unknown_id(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        assert cl.get_entry("nonexistent") is None

    def test_returns_entry_by_id(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        entry = cl.record("p1", "created", "actor")
        found = cl.get_entry(entry.id)
        assert found is not None
        assert found.id == entry.id

    def test_returns_correct_entry_among_multiple(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        e1 = cl.record("p1", "created", "actor")
        e2 = cl.record("p1", "updated", "actor")
        assert cl.get_entry(e1.id).id == e1.id
        assert cl.get_entry(e2.id).id == e2.id


# ---------------------------------------------------------------------------
# ChangeLog — get_change_stats
# ---------------------------------------------------------------------------


class TestGetChangeStats:
    def test_empty_returns_zeros(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        stats = cl.get_change_stats()
        assert stats["total_changes"] == 0
        assert stats["total_pages"] == 0
        assert stats["changes_by_type"] == {}
        assert stats["most_changed"] == []

    def test_counts_are_accurate(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "alice")
        cl.record("p1", "updated", "bob")
        cl.record("p2", "created", "alice")
        stats = cl.get_change_stats()
        assert stats["total_changes"] == 3
        assert stats["total_pages"] == 2
        assert stats["changes_by_type"]["created"] == 2
        assert stats["changes_by_type"]["updated"] == 1
        assert stats["changes_by_actor"]["alice"] == 2
        assert stats["changes_by_actor"]["bob"] == 1

    def test_most_changed_sorted_by_count(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        for _ in range(3):
            cl.record("p1", "updated", "actor")
        cl.record("p2", "created", "actor")
        stats = cl.get_change_stats()
        assert stats["most_changed"][0]["page_id"] == "p1"
        assert stats["most_changed"][0]["count"] == 3


# ---------------------------------------------------------------------------
# ChangeLog — format_diff / format_page_diff
# ---------------------------------------------------------------------------


class TestFormatDiff:
    def test_format_diff_contains_key_fields(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        fc = FieldChange("title", None, "Hello World", "added")
        entry = cl.record("page-1", "created", "extractor", changes=[fc], reason="initial")
        text = cl.format_diff(entry)
        assert "page-1" in text
        assert "created" in text
        assert "extractor" in text
        assert "initial" in text
        assert "title" in text
        assert "Hello World" in text

    def test_format_diff_no_changes_label(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        entry = cl.record("p1", "created", "actor")
        text = cl.format_diff(entry)
        assert "none recorded" in text

    def test_format_page_diff_no_history(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        text = cl.format_page_diff("nonexistent-page")
        assert "No change history" in text

    def test_format_page_diff_includes_entries(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        cl.record("p1", "updated", "actor")
        text = cl.format_page_diff("p1")
        assert "p1" in text
        assert "created" in text
        assert "updated" in text

    def test_format_page_diff_time_filter(self, tmp_path):
        cl = ChangeLog(changelog_dir=tmp_path / "cl")
        cl.record("p1", "created", "actor")
        # Filter to a future window — should return "no changes in range"
        future = datetime.now(UTC) + timedelta(hours=1)
        text = cl.format_page_diff("p1", from_dt=future)
        assert "No changes found" in text


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormatHelpers:
    def test_fmt_val_none(self):
        assert _fmt_val(None) == "(none)"

    def test_fmt_val_truncates_long_strings(self):
        long_str = "x" * 200
        result = _fmt_val(long_str)
        assert len(result) <= 121  # 120 + ellipsis char

    def test_fmt_val_string_not_repr(self):
        # Strings should not be wrapped in quotes
        result = _fmt_val("hello")
        assert result == "hello"

    def test_fmt_val_list_uses_repr(self):
        result = _fmt_val(["a", "b"])
        assert result.startswith("[")

    def test_format_field_change_added(self):
        fc = FieldChange("tags", None, ["x"], "added")
        lines = _format_field_change(fc)
        assert any(line.startswith("  +") for line in lines)

    def test_format_field_change_removed(self):
        fc = FieldChange("tags", ["x"], None, "removed")
        lines = _format_field_change(fc)
        assert any(line.startswith("  -") for line in lines)

    def test_format_field_change_modified(self):
        fc = FieldChange("title", "old", "new", "modified")
        lines = _format_field_change(fc)
        assert any(line.startswith("  ~") for line in lines)
        assert any("old" in line for line in lines)
        assert any("new" in line for line in lines)
