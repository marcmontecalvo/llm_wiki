#!/bin/bash
set -e

# Initialize wiki data directory structure if not yet present
if [ ! -d "/wiki/inbox" ]; then
    echo "Initializing wiki directory structure..."
    mkdir -p /wiki/inbox
    mkdir -p /wiki/shared/concepts
    mkdir -p /wiki/shared/entities
    chown -R llmwiki:llmwiki /wiki
fi

# Ensure config directory exists inside wiki data
mkdir -p /wiki/config
# Copy bundled config defaults (read-only) into /wiki/config if not overridden
if [ -d "/config/ro" ]; then
    cp -n "/config/ro/daemon.yaml" "/wiki/config/daemon.yaml" 2>/dev/null || true
    cp -n "/config/ro/domains.yaml" "/wiki/config/domains.yaml" 2>/dev/null || true
    cp -n "/config/ro/models.yaml" "/wiki/config/models.yaml" 2>/dev/null || true
    cp -n "/config/ro/routing.yaml" "/wiki/config/routing.yaml" 2>/dev/null || true
fi
chown -R llmwiki:llmwiki /wiki/config /wiki/shared

# On first run, copy custom default config if not already present
# (Only runs when /wiki/config is fresh — container restarts skip this)
if [ -d "/app/config.custom" ]; then
    for f in /app/config.custom/*.yaml; do
        [ -f "$f" ] || continue
        fname="$(basename "$f")"
        [ -f "/wiki/config/$fname" ] || cp "$f" "/wiki/config/$fname"
    done
    chown -R llmwiki:llmwiki /wiki/config
    rm -rf /app/config.custom
fi

exec "$@"
