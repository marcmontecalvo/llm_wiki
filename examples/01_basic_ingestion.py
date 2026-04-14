"""
Basic Ingestion Workflow

This example demonstrates how to add content to the wiki system
through the inbox and process it through the pipeline.
"""

from pathlib import Path

from llm_wiki.ingest.router import DomainRouter
from llm_wiki.ingest.watcher import InboxWatcher

# Setup paths
wiki_base = Path("wiki_system")
inbox = wiki_base / "inbox"

# Ensure directories exist
inbox.mkdir(parents=True, exist_ok=True)

# Example 1: Drop a simple markdown file
simple_content = """---
title: Python Programming
domain: tech
tags:
  - python
  - programming
---

# Python Programming

Python is a high-level, interpreted programming language known for its
simplicity and readability.

## Key Features

- Easy to learn syntax
- Large standard library
- Dynamic typing
- Strong community support

Source: https://www.python.org/
"""

simple_file = inbox / "python-programming.md"
simple_file.write_text(simple_content)

print(f"Created: {simple_file}")

# Example 2: Drop a file without frontmatter (will be added during processing)
plain_content = """# Docker Containers

Docker is a platform for developing, shipping, and running applications
in containers.

Containers package software with its dependencies, making it portable
across different environments.
"""

plain_file = inbox / "docker.txt"
plain_file.write_text(plain_content)

print(f"Created: {plain_file}")

# Example 3: Process inbox with watcher
watcher = InboxWatcher(wiki_base=wiki_base)
router = DomainRouter(wiki_base=wiki_base)

print("\nProcessing inbox...")

# The watcher would normally run as a daemon, but we can trigger it manually
for file_path in inbox.iterdir():
    if file_path.is_file() and not file_path.name.startswith("."):
        print(f"Processing: {file_path.name}")

        # Adapter selection happens automatically based on file extension
        # Files are normalized, routed to appropriate domain, and moved to queue

        # In production, this happens via the daemon:
        # from llm_wiki.daemon.jobs.inbox_watcher import InboxWatcherJob
        # job = InboxWatcherJob(wiki_base)
        # job.execute()

print("\nFiles processed and moved to domain queues.")
print("Run extraction pipeline next to enrich metadata and move to pages/.")
