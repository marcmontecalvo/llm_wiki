#!/bin/bash
set -e

# Initialize wiki data directory structure if not yet present
if [ ! -d "/wiki_system/inbox" ]; then
    echo "Initializing wiki directory structure..."
    mkdir -p /wiki_system/inbox
    mkdir -p /wiki_system/shared/concepts
    mkdir -p /wiki_system/shared/entities
    mkdir -p /wiki_system/state
    chown -R llmwiki:llmwiki /wiki_system
fi

# Ensure config directory exists inside wiki data
mkdir -p /wiki_system/config
# Copy bundled config defaults (read-only) into /wiki_system/config if not overridden
if [ -d "/config/ro" ]; then
    cp -n /config/ro/*.yaml /wiki_system/config/ 2>/dev/null || true
fi
chown -R llmwiki:llmwiki /wiki_system/config /wiki_system/shared

exec "$@"
