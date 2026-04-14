"""Tests for daemon state persistence."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_wiki.daemon.state import DaemonState


class TestDaemonState:
    """Tests for DaemonState class."""

    def test_init_creates_default_path(self):
        """Test initialization creates default state file path."""
        state = DaemonState()

        assert state.state_file == Path("wiki_system") / "state" / "daemon_state.json"
        assert state.state_file.parent.exists()

        # Cleanup
        if state.state_file.exists():
            state.state_file.unlink()

    def test_init_with_custom_path(self, temp_dir: Path):
        """Test initialization with custom path."""
        state_file = temp_dir / "custom_state.json"
        state = DaemonState(state_file)

        assert state.state_file == state_file

    def test_init_creates_parent_directory(self, temp_dir: Path):
        """Test initialization creates parent directories."""
        state_file = temp_dir / "nested" / "dir" / "state.json"
        state = DaemonState(state_file)

        assert state.state_file.parent.exists()

    def test_initial_state_structure(self, temp_dir: Path):
        """Test initial state has correct structure."""
        state = DaemonState(temp_dir / "state.json")

        assert state.state["version"] == 1
        assert state.state["last_updated"] is None
        assert state.state["job_last_run"] == {}
        assert state.state["inbox_files"] == {}

    def test_save_creates_file(self, temp_dir: Path):
        """Test save creates state file."""
        state_file = temp_dir / "state.json"
        state = DaemonState(state_file)

        state.save()

        assert state_file.exists()

    def test_save_writes_valid_json(self, temp_dir: Path):
        """Test save writes valid JSON."""
        state_file = temp_dir / "state.json"
        state = DaemonState(state_file)

        state.save()

        # Should be valid JSON
        with open(state_file) as f:
            data = json.load(f)

        assert data["version"] == 1
        assert "last_updated" in data

    def test_save_updates_timestamp(self, temp_dir: Path):
        """Test save updates last_updated timestamp."""
        state_file = temp_dir / "state.json"
        state = DaemonState(state_file)

        state.save()

        assert state.state["last_updated"] is not None
        # Should be recent timestamp
        timestamp = datetime.fromisoformat(state.state["last_updated"])
        assert (datetime.now(UTC) - timestamp).seconds < 5

    def test_load_nonexistent_file(self, temp_dir: Path, caplog):
        """Test load with nonexistent file starts with empty state."""
        import logging

        caplog.set_level(logging.INFO)
        state_file = temp_dir / "nonexistent.json"
        state = DaemonState(state_file)

        state.load()

        assert "No state file found" in caplog.text
        assert state.state["job_last_run"] == {}

    def test_load_valid_state(self, temp_dir: Path):
        """Test load reads valid state file."""
        state_file = temp_dir / "state.json"

        # Create a valid state file
        test_state = {
            "version": 1,
            "last_updated": datetime.now(UTC).isoformat(),
            "job_last_run": {"job1": "2026-04-14T10:00:00+00:00"},
            "inbox_files": {
                "file1.md": {"status": "completed", "updated_at": "2026-04-14T10:00:00+00:00"}
            },
        }
        with open(state_file, "w") as f:
            json.dump(test_state, f)

        state = DaemonState(state_file)
        state.load()

        assert state.state["job_last_run"]["job1"] == "2026-04-14T10:00:00+00:00"
        assert state.state["inbox_files"]["file1.md"]["status"] == "completed"

    def test_load_corrupted_file(self, temp_dir: Path, caplog):
        """Test load handles corrupted JSON."""
        state_file = temp_dir / "corrupted.json"
        state_file.write_text("{ invalid json }")

        state = DaemonState(state_file)
        state.load()

        assert "Corrupted state file" in caplog.text
        # Should have empty state
        assert state.state["job_last_run"] == {}

    def test_load_wrong_version(self, temp_dir: Path, caplog):
        """Test load handles version mismatch."""
        state_file = temp_dir / "state.json"

        # Create state with wrong version
        test_state = {
            "version": 999,
            "last_updated": datetime.now(UTC).isoformat(),
            "job_last_run": {},
            "inbox_files": {},
        }
        with open(state_file, "w") as f:
            json.dump(test_state, f)

        state = DaemonState(state_file)
        state.load()

        assert "version mismatch" in caplog.text
        # Should reset to empty state
        assert state.state["version"] == 1

    def test_load_stale_state(self, temp_dir: Path, caplog):
        """Test load detects stale state."""
        state_file = temp_dir / "state.json"

        # Create state 60 days old
        old_time = datetime.now(UTC) - timedelta(days=60)
        test_state = {
            "version": 1,
            "last_updated": old_time.isoformat(),
            "job_last_run": {},
            "inbox_files": {},
        }
        with open(state_file, "w") as f:
            json.dump(test_state, f)

        state = DaemonState(state_file)
        state.load()

        assert "stale" in caplog.text

    def test_roundtrip(self, temp_dir: Path):
        """Test save and load roundtrip."""
        state_file = temp_dir / "state.json"
        state1 = DaemonState(state_file)

        # Set some state
        now = datetime.now(UTC)
        state1.set_job_last_run("job1", now)
        state1.set_inbox_file_status("file1.md", "completed")

        # Save
        state1.save()

        # Load in new instance
        state2 = DaemonState(state_file)
        state2.load()

        # Should match
        assert state2.get_job_last_run("job1") is not None
        assert state2.get_inbox_file_status("file1.md") == "completed"

    def test_set_job_last_run(self, temp_dir: Path):
        """Test setting job last run time."""
        state = DaemonState(temp_dir / "state.json")
        now = datetime.now(UTC)

        state.set_job_last_run("test_job", now)

        assert "test_job" in state.state["job_last_run"]
        assert state.state["job_last_run"]["test_job"] == now.isoformat()

    def test_set_job_last_run_default_timestamp(self, temp_dir: Path):
        """Test setting job last run with default timestamp."""
        state = DaemonState(temp_dir / "state.json")

        state.set_job_last_run("test_job")

        assert "test_job" in state.state["job_last_run"]
        # Should be recent
        timestamp = datetime.fromisoformat(state.state["job_last_run"]["test_job"])
        assert (datetime.now(UTC) - timestamp).seconds < 5

    def test_get_job_last_run(self, temp_dir: Path):
        """Test getting job last run time."""
        state = DaemonState(temp_dir / "state.json")
        now = datetime.now(UTC)

        state.set_job_last_run("test_job", now)
        result = state.get_job_last_run("test_job")

        assert result is not None
        # Timestamps should be very close (within 1 second)
        assert abs((result - now).total_seconds()) < 1

    def test_get_job_last_run_nonexistent(self, temp_dir: Path):
        """Test getting nonexistent job returns None."""
        state = DaemonState(temp_dir / "state.json")

        result = state.get_job_last_run("nonexistent")

        assert result is None

    def test_set_inbox_file_status(self, temp_dir: Path):
        """Test setting inbox file status."""
        state = DaemonState(temp_dir / "state.json")

        state.set_inbox_file_status("test.md", "processing")

        assert "test.md" in state.state["inbox_files"]
        assert state.state["inbox_files"]["test.md"]["status"] == "processing"
        assert "updated_at" in state.state["inbox_files"]["test.md"]

    def test_get_inbox_file_status(self, temp_dir: Path):
        """Test getting inbox file status."""
        state = DaemonState(temp_dir / "state.json")

        state.set_inbox_file_status("test.md", "completed")
        result = state.get_inbox_file_status("test.md")

        assert result == "completed"

    def test_get_inbox_file_status_nonexistent(self, temp_dir: Path):
        """Test getting nonexistent file returns None."""
        state = DaemonState(temp_dir / "state.json")

        result = state.get_inbox_file_status("nonexistent.md")

        assert result is None

    def test_get_all_inbox_files(self, temp_dir: Path):
        """Test getting all inbox files."""
        state = DaemonState(temp_dir / "state.json")

        state.set_inbox_file_status("file1.md", "completed")
        state.set_inbox_file_status("file2.md", "processing")

        result = state.get_all_inbox_files()

        assert len(result) == 2
        assert "file1.md" in result
        assert "file2.md" in result

    def test_clear_inbox_file(self, temp_dir: Path):
        """Test clearing an inbox file."""
        state = DaemonState(temp_dir / "state.json")

        state.set_inbox_file_status("test.md", "completed")
        state.clear_inbox_file("test.md")

        assert "test.md" not in state.state["inbox_files"]

    def test_clear_inbox_file_nonexistent(self, temp_dir: Path):
        """Test clearing nonexistent file doesn't error."""
        state = DaemonState(temp_dir / "state.json")

        state.clear_inbox_file("nonexistent.md")  # Should not raise

    def test_clear_old_inbox_files(self, temp_dir: Path):
        """Test clearing old inbox files."""
        state = DaemonState(temp_dir / "state.json")

        # Add old file
        old_time = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        state.state["inbox_files"]["old.md"] = {"status": "completed", "updated_at": old_time}

        # Add recent file
        state.set_inbox_file_status("recent.md", "completed")

        # Clear files older than 7 days
        count = state.clear_old_inbox_files(days=7)

        assert count == 1
        assert "old.md" not in state.state["inbox_files"]
        assert "recent.md" in state.state["inbox_files"]

    def test_clear_old_inbox_files_invalid_timestamp(self, temp_dir: Path):
        """Test clearing files with invalid timestamps."""
        state = DaemonState(temp_dir / "state.json")

        # Add file with invalid timestamp
        state.state["inbox_files"]["invalid.md"] = {"status": "completed", "updated_at": "invalid"}

        count = state.clear_old_inbox_files(days=7)

        # Should remove file with invalid timestamp
        assert count == 1
        assert "invalid.md" not in state.state["inbox_files"]
