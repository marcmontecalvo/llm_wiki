# LLM Wiki — Deployment Guide

## Deployment Model

LLM Wiki is a **local-first, single-user application**. There is no cloud backend. The daemon runs on your local machine (or a homelab server) and manages a directory of markdown files. The recommended deployment is:

1. Run on a machine that stays on (Mac, Linux server, Raspberry Pi, homelab VM)
2. Store `wiki_system/` in a git-tracked directory for versioning
3. Optionally expose the CLI over Tailscale or SSH for remote access

## Installation

```bash
# From source (recommended for development)
git clone <repo-url>
cd llm_wiki
uv sync

# Install entry point
uv run llm-wiki --help   # Verifies install

# Vector search is always available (FAISS + sentence-transformers are core dependencies)
```

## Initial Setup

```bash
# 1. Initialize wiki directory structure
uv run llm-wiki init
# Creates wiki_system/ with all required subdirectories

# 2. Configure your domains
nano config/domains.yaml   # Define your knowledge domains

# 3. Configure LLM provider
nano config/models.yaml    # Set provider, model, API key location

# 4. Configure routing
nano config/routing.yaml   # Define source → domain routing rules

# 5. Verify config is valid — the daemon refuses to start with invalid config,
# so just start it and watch for errors:
uv run llm-wiki daemon start
```

## LLM Provider Setup

The daemon uses an OpenAI-compatible API for all LLM operations. Configure in `config/models.yaml`:

### OpenAI

```yaml
extraction:
  provider: openai
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY   # Set OPENAI_API_KEY in environment
  temperature: 0.1
  max_tokens: 2000
```

```bash
export OPENAI_API_KEY=sk-...
uv run llm-wiki daemon start
```

### Anthropic (Claude)

```yaml
extraction:
  provider: anthropic
  model: claude-3-5-haiku-20241022
  base_url: https://api.anthropic.com/v1
  api_key_env: ANTHROPIC_API_KEY
```

### Ollama (Local)

```bash
# Start Ollama first
ollama serve
ollama pull mistral
```

```yaml
extraction:
  provider: ollama
  model: mistral
  base_url: http://localhost:11434/v1
  api_key: ollama   # Ollama doesn't use real keys
```

### LM Studio

```yaml
extraction:
  provider: lm_studio
  model: local-model
  base_url: http://localhost:1234/v1
  api_key: lm-studio
```

### Claude Agent SDK

```bash
uv sync --extra claude-agent
```

```yaml
extraction:
  provider: claude_agent_sdk
  model: claude-opus-4-7
```

## Running the Daemon

### Foreground (development/testing)

```bash
uv run llm-wiki daemon start
# Ctrl-C to stop
```

### Background with nohup

```bash
nohup uv run llm-wiki daemon start > logs/daemon.log 2>&1 &
echo $! > daemon.pid

# Stop
kill $(cat daemon.pid)
```

### systemd (Linux server)

```ini
# /etc/systemd/system/llm-wiki.service
[Unit]
Description=LLM Wiki Daemon
After=network.target

[Service]
Type=simple
User=marc
WorkingDirectory=/home/marc/repos/llm_wiki
ExecStart=/home/marc/.local/bin/uv run llm-wiki daemon start
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable llm-wiki
sudo systemctl start llm-wiki
sudo systemctl status llm-wiki
journalctl -u llm-wiki -f   # Follow logs
```

### launchd (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.marcmontecalvo.llm-wiki.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.marcmontecalvo.llm-wiki</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/marc/.local/bin/uv</string>
        <string>run</string>
        <string>llm-wiki</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/marc/repos/llm_wiki</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/marc/repos/llm_wiki/wiki_system/logs/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/marc/repos/llm_wiki/wiki_system/logs/daemon-error.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.marcmontecalvo.llm-wiki.plist
launchctl start com.marcmontecalvo.llm-wiki
```

## Daemon Configuration

Edit `config/daemon.yaml`:

```yaml
inbox_poll_seconds: 15          # How often to scan inbox/new/
migrate_queue_every_minutes: 15 # How often to move queue → pages
retry_failed_ingests_every_minutes: 30
rebuild_index_every_minutes: 30
lint_every_minutes: 60
export_every_minutes: 60
max_parallel_jobs: 2            # Max concurrent background jobs
log_level: INFO                 # DEBUG for verbose output
review_queue_enabled: true      # Set false to disable review queue population
```

**Important**: `max_parallel_jobs: 2` is intentional. Increasing this without first fixing the index write mutex (P0-2) risks JSON corruption.

## Monitoring

```bash
# Daemon status and job health
uv run llm-wiki daemon status

# List jobs with last-run times and next scheduled run
uv run llm-wiki daemon jobs

# Force-run a specific job
uv run llm-wiki govern run index-rebuild
uv run llm-wiki govern run governance-check
uv run llm-wiki govern run export

# View latest governance report
ls -lt wiki_system/reports/ | head -5
cat wiki_system/reports/governance_latest.md

# View ingestion stats
uv run llm-wiki ingest stats
```

## Session Capture Integration

For Claude Code users, install the session capture hooks:

```bash
# Install for current project (Claude Code project scope)
uv run llm-wiki hooks install --scope project

# Install globally for all projects
uv run llm-wiki hooks install --scope user
```

This installs `SessionEnd` and `PreCompact` hooks that automatically drop Claude Code session transcripts into `inbox/new/` at the end of each session. The daemon picks them up within 15 seconds and ingests them into the appropriate domain.

## Backup and Versioning

All state is in files:

```bash
# The complete wiki lives in wiki_system/
# Suggested: track it in git

cd wiki_system
git init
git add domains/ shared/     # Track page content
# Don't track index/ or exports/ — these are derived
echo "index/" >> .gitignore
echo "exports/" >> .gitignore
echo "logs/" >> .gitignore
git commit -m "initial wiki"
```

Or use the parent repo's git tracking:

```bash
# Add wiki_system/domains/ and wiki_system/shared/ to .gitignore exceptions
# if the parent repo ignores wiki_system/
```

## Disk Space

Rough estimates at steady state:

| Path | Content | Size estimate |
|------|---------|---------------|
| `wiki_system/domains/` | All wiki pages (markdown) | ~1MB per 1,000 pages |
| `wiki_system/index/fulltext.json` | TF-IDF inverted index | ~5MB per 10,000 pages |
| `wiki_system/index/vector_index.faiss` | FAISS float32 vectors | ~1.5MB per 1,000 pages |
| `wiki_system/exports/` | Generated exports | ~2MB per 1,000 pages |
| `sentence-transformers` model | `all-MiniLM-L6-v2` | ~80MB (one-time download) |

## Multi-container deployment (Honcho + LLM-Wiki)

When running Honcho and LLM-Wiki as separate containers, they communicate over Docker's default bridge network. Each component is independently deployable and the wiki works perfectly without Honcho.

### Environment variables for integration

| Variable | Purpose | Required if |
|----------|---------|-------------|
| `HONCHO_URL` | Base URL for the Honcho service (e.g. `http://honcho:8000`) | Honcho is in a separate container |
| `WIKI_HONCHO_PUSH: true` | Enables the daemon job that pushes wiki exports to Honcho | You want auto-sync |
| `HONCHO_API_KEY` | API key passed as `Authorization: Bearer` header when pushing to remote Honcho | Remote push with auth |

### How it works

1. **Export job** runs every 60 minutes and writes `llms.txt` + `graph.json` to `wiki_system/exports/`
2. **Honcho push job** runs 5 minutes after export (configurable via `honcho_push_offset_minutes`) and reads those files
3. Push is HTTP POST to `{push_url}/v1/honcho/wiki-bundle` (remote mode) or honcho SDK (local mode)

### Network topology

```
[Docker network "default"]
  honcho:8000 <-- HTTP POST --> llm-wiki:3050
  llm-wiki:3050 <-- HTTP GET --> honcho:8000 (/health)
```

The wiki can run standalone — without Honcho configured:
- `/v1/honcho/status` returns `available: false` (no error)
- Honcho push daemon job logs `"skipped"` and continues
- All wiki, MCP, and facts API functionality works independently

## Security Notes

- **No authentication by default** — the daemon is local-only, binds to `0.0.0.0` inside the container with port exposure controlled by docker-compose. For network exposure, use a reverse proxy with TLS or tunnel via Tailscale/SSH.
- **UI auth**: When `webui_enabled` is true, the web UI uses HTTP Basic Auth (via `WIKI_UI_USER` / `WIKI_UI_PASSWORD` env vars).
- **API keys**: Set via environment variables, never hardcode in config files
- **LLM API calls**: All extraction/integration calls go to your configured LLM provider; documents you ingest are sent to that provider
- **Honcho integration**: If running alongside Honcho, Honcho uses its own auth (JWT for self-hosted, API key for managed). Do not reuse auth credentials between the two services.

## Known Operational Issues

| Issue | Impact | Workaround |
|-------|--------|-----------|
| LLM call no timeout | Worker thread blocks indefinitely on hung LLM | Restart daemon if stuck |

## Upgrading

```bash
git pull
uv sync             # Update dependencies
uv run pytest       # Verify nothing broke
uv run llm-wiki govern run index-rebuild   # Rebuild indexes after upgrade
```
