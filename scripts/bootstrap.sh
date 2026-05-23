#!/usr/bin/env bash
set -euo pipefail

# Get the script directory (works with symlinks)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Wiki base directory — defaults to wiki_system for backwards compatibility
WIKI_DIR="${WIKI_BASE:-wiki_system}"

# Use Python to parse domains from config/domains.yaml
# Use uv run python to ensure dependencies are available.
# --project points uv to the pyproject.toml even when the
# caller's cwd has no project file (e.g. pytest tmp_path).
DOMAINS=$(uv run --project "$REPO_ROOT/pyproject.toml" python << 'EOF'
import yaml
from pathlib import Path

config_file = Path("config/domains.yaml")
if config_file.exists():
    with open(config_file) as f:
        config = yaml.safe_load(f)
        domains = [d["id"] for d in config.get("domains", [])]
        print(" ".join(domains))
else:
    # Fallback to defaults if config doesn't exist
    print("general tech")
EOF
)

# Create domain directories from config
for domain in $DOMAINS; do
    mkdir -p "${WIKI_DIR}/domains/${domain}/pages"
    mkdir -p "${WIKI_DIR}/domains/${domain}/queue"
done

# Create other required directories
mkdir -p "${WIKI_DIR}/inbox"
mkdir -p "${WIKI_DIR}/index"
mkdir -p "${WIKI_DIR}/exports"
mkdir -p "${WIKI_DIR}/reports"
mkdir -p "${WIKI_DIR}/logs"
mkdir -p "${WIKI_DIR}/state"

echo "Base directories created in ${WIKI_DIR} for domains: $DOMAINS"
