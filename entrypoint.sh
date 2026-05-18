#!/bin/bash
set -e

# Initialize wiki data directory structure if not yet present
if [ ! -d "/wiki/inbox" ]; then
    echo "Initializing wiki directory structure..."
    mkdir -p /wiki/inbox
    mkdir -p /wiki/shared/concepts
    mkdir -p /wiki/shared/entities
    mkdir -p /wiki/state
    chown -R llmwiki:llmwiki /wiki
fi

# Ensure config directory exists inside wiki data
mkdir -p /wiki/config
# Copy bundled config defaults (read-only) into /wiki/config if not overridden
if [ -d "/config/ro" ]; then
    cp -n /config/ro/*.yaml /wiki/config/ 2>/dev/null || true
fi
chown -R llmwiki:llmwiki /wiki/config /wiki/shared

exec "$@"
