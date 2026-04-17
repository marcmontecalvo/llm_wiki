"""Tests for the `llm-wiki hooks install/uninstall` CLI."""

import json
import os
import sys
from pathlib import Path

from click.testing import CliRunner

from llm_wiki.cli import main


class TestHooksInstall:
    """Tests for `llm-wiki hooks install`."""

    def test_dry_run_outputs_json(self, tmp_path: Path):
        """--dry-run prints merged settings without writing."""
        runner = CliRunner()
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(
                main,
                ["hooks", "install", "--scope", "project", "--dry-run"],
            )
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        # Parse the JSON output
        data = json.loads(result.output)
        assert "hooks" in data
        assert "SessionEnd" in data["hooks"]
        assert "PreCompact" in data["hooks"]
        # No file should have been created
        assert not (tmp_path / ".claude" / "settings.json").exists()

    def test_install_project_creates_settings(self, tmp_path: Path):
        """Installing at project scope creates .claude/settings.json."""
        runner = CliRunner()
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(
                main, ["hooks", "install", "--scope", "project"]
            )
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()

        data = json.loads(settings.read_text(encoding="utf-8"))
        assert "hooks" in data
        assert "SessionEnd" in data["hooks"]
        assert "PreCompact" in data["hooks"]
        # Entries contain our capture_session.py
        session_entry = data["hooks"]["SessionEnd"][0]
        cmd = session_entry["hooks"][0]["command"]
        assert "capture_session.py" in cmd
        # F3: command uses the current interpreter, not bare "python".
        assert sys.executable in cmd
        # F5: SessionEnd/PreCompact entries must not carry "matcher".
        assert "matcher" not in session_entry

    def test_install_preserves_unrelated_hooks(self, tmp_path: Path):
        """Existing hook entries unrelated to llm-wiki are preserved."""
        runner = CliRunner()
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = settings_dir / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionEnd": [
                            {
                                "matcher": "",
                                "hooks": [
                                    {"type": "command", "command": "echo unrelated"}
                                ],
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(main, ["hooks", "install", "--scope", "project"])
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        data = json.loads(settings.read_text(encoding="utf-8"))
        commands = [
            h["command"]
            for item in data["hooks"]["SessionEnd"]
            for h in item["hooks"]
        ]
        assert any("echo unrelated" in c for c in commands)
        assert any("capture_session.py" in c for c in commands)

    def test_install_is_idempotent(self, tmp_path: Path):
        """Running install twice does not duplicate llm-wiki entries."""
        runner = CliRunner()
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            runner.invoke(main, ["hooks", "install", "--scope", "project"])
            runner.invoke(main, ["hooks", "install", "--scope", "project"])
        finally:
            os.chdir(cwd)

        data = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        capture_count = sum(
            1
            for item in data["hooks"]["SessionEnd"]
            for h in item["hooks"]
            if "capture_session.py" in h["command"]
        )
        assert capture_count == 1


class TestHooksUninstall:
    """Tests for `llm-wiki hooks uninstall`."""

    def test_uninstall_removes_entries(self, tmp_path: Path):
        """Uninstall removes llm-wiki hook entries but leaves others."""
        runner = CliRunner()
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            runner.invoke(main, ["hooks", "install", "--scope", "project"])
            # Append an unrelated hook after install
            settings = tmp_path / ".claude" / "settings.json"
            data = json.loads(settings.read_text(encoding="utf-8"))
            data["hooks"]["SessionEnd"].append(
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": "echo keep-me"}],
                }
            )
            settings.write_text(json.dumps(data), encoding="utf-8")

            result = runner.invoke(
                main, ["hooks", "uninstall", "--scope", "project"]
            )
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        data = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        # SessionEnd still has the unrelated hook; capture_session.py gone.
        remaining = data.get("hooks", {}).get("SessionEnd", [])
        commands = [h["command"] for item in remaining for h in item["hooks"]]
        assert any("echo keep-me" in c for c in commands)
        assert not any("capture_session.py" in c for c in commands)
        # PreCompact should be removed entirely (no other entries were there)
        assert "PreCompact" not in data.get("hooks", {})

    def test_uninstall_when_no_settings(self, tmp_path: Path):
        """Uninstall with no settings.json is a no-op success."""
        runner = CliRunner()
        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(
                main, ["hooks", "uninstall", "--scope", "project"]
            )
        finally:
            os.chdir(cwd)
        assert result.exit_code == 0
