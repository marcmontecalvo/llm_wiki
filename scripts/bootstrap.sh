#!/usr/bin/env bash
set -euo pipefail

mkdir -p wiki_system/domains/{vulpine-solutions,home-assistant,homelab,personal,general}
mkdir -p wiki_system/shared/{concepts,entities,synthesis}
mkdir -p wiki_system/inbox/{new,processing,failed,done}
mkdir -p wiki_system/exports/{json,graph,site}
mkdir -p wiki_system/logs
mkdir -p wiki_system/state

echo "Base directories created."
