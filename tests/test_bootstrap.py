"""
Tests for bootstrap script.

Verifies that bootstrap.sh correctly reads domains from config/domains.yaml.
"""

import subprocess
from pathlib import Path


def test_bootstrap_reads_from_config(tmp_path):
    """Test that bootstrap.sh creates directories based on config/domains.yaml."""
    # Create a temporary config file
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_file = config_dir / "domains.yaml"
    config_file.write_text("""domains:
  - id: test-domain-1
    title: Test Domain 1
    description: First test domain
    owners: [user]
    promote_to_shared: false
  - id: test-domain-2
    title: Test Domain 2
    description: Second test domain
    owners: [user]
    promote_to_shared: false
""")

    # Run bootstrap script in temp directory
    script_path = Path(__file__).parent.parent / "scripts" / "bootstrap.sh"

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    # Check script succeeded
    assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"

    # Verify correct domains were created
    wiki_system = tmp_path / "wiki_system" / "domains"
    assert wiki_system.exists()

    assert (wiki_system / "test-domain-1" / "pages").exists()
    assert (wiki_system / "test-domain-1" / "queue").exists()
    assert (wiki_system / "test-domain-2" / "pages").exists()
    assert (wiki_system / "test-domain-2" / "queue").exists()

    # Verify hardcoded domains are NOT created
    assert not (wiki_system / "vulpine-solutions").exists()
    assert not (wiki_system / "homelab").exists()

    # Verify output mentions the correct domains
    assert "test-domain-1" in result.stdout
    assert "test-domain-2" in result.stdout


def test_bootstrap_creates_standard_directories(tmp_path):
    """Test that bootstrap.sh creates all required standard directories."""
    # Create minimal config
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_file = config_dir / "domains.yaml"
    config_file.write_text("""domains:
  - id: general
    title: General
    description: General domain
    owners: [system]
    promote_to_shared: false
""")

    # Run bootstrap script
    script_path = Path(__file__).parent.parent / "scripts" / "bootstrap.sh"

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    # Verify standard directories exist
    wiki_system = tmp_path / "wiki_system"
    assert (wiki_system / "inbox").exists()
    assert (wiki_system / "index").exists()
    assert (wiki_system / "exports").exists()
    assert (wiki_system / "reports").exists()
    assert (wiki_system / "logs").exists()
    assert (wiki_system / "state").exists()


def test_bootstrap_fallback_without_config(tmp_path):
    """Test that bootstrap.sh has fallback behavior if config is missing."""
    # Don't create a config file

    # Run bootstrap script
    script_path = Path(__file__).parent.parent / "scripts" / "bootstrap.sh"

    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    # Should create fallback domains
    wiki_system = tmp_path / "wiki_system" / "domains"
    assert (wiki_system / "general").exists()
    assert (wiki_system / "tech").exists()
