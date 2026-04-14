#!/usr/bin/env bash
set -euo pipefail

# Get the script directory (works with symlinks)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Use Python to parse domains from config/domains.yaml
# Use uv run python to ensure dependencies are available
DOMAINS=$(uv run python << 'EOF'
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
    mkdir -p "wiki_system/domains/${domain}/pages"
    mkdir -p "wiki_system/domains/${domain}/queue"
done

# Create other required directories
mkdir -p wiki_system/inbox
mkdir -p wiki_system/index
mkdir -p wiki_system/exports
mkdir -p wiki_system/reports
mkdir -p wiki_system/logs
mkdir -p wiki_system/state

echo "Base directories created for domains: $DOMAINS"
