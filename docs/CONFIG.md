# Configuration Reference

Configuration file formats and options for the LLM wiki system.

## Configuration Files

All configuration files are in the `config/` directory:

```
config/
├── domains.yaml    # Domain definitions (SOURCE OF TRUTH for domains)
├── routing.yaml    # Content routing rules
├── models.yaml     # LLM provider settings
└── daemon.yaml     # Daemon job schedules
```

---

## `domains.yaml`

**Source of Truth:** Domain structure and metadata.

**Format:**
```yaml
domains:
  - id: domain-id                # Unique domain identifier (kebab-case)
    title: Domain Title          # Human-readable name
    description: Brief description
    owners: [owner1, owner2]     # Domain owners
    promote_to_shared: boolean   # Whether pages can be promoted to shared (future)
```

**Example:**
```yaml
domains:
  - id: vulpine-solutions
    title: Vulpine Solutions
    description: MSP, operations, sales, security, client delivery
    owners: [user]
    promote_to_shared: true

  - id: home-assistant
    title: Home Assistant
    description: Automation, voice assistant, ESP32, local AI, sensors
    owners: [user]
    promote_to_shared: true

  - id: homelab
    title: Homelab
    description: Proxmox, k3s, storage, networking, GPUs, services
    owners: [user]
    promote_to_shared: true

  - id: personal
    title: Personal
    description: Family logistics, hobbies, plans, notes
    owners: [user]
    promote_to_shared: false

  - id: general
    title: General
    description: Fallback bucket for unclassified content
    owners: [system]
    promote_to_shared: false
```

**Field Reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (kebab-case, lowercase with hyphens) |
| `title` | string | Yes | Display name for the domain |
| `description` | string | Yes | Brief description of domain scope |
| `owners` | list[string] | Yes | List of domain owners |
| `promote_to_shared` | boolean | Yes | Whether pages can be promoted to shared space (future feature) |

**Important:**
- Domain IDs must be unique
- IDs should be stable (changing them breaks references)
- The `general` domain is recommended as a fallback
- Bootstrap script reads this file to create directory structure

---

## `routing.yaml`

**Source of Truth:** Content routing rules for inbox processing.

**Format:**
```yaml
routing_rules:
  - pattern: "pattern-string"    # File path pattern or content pattern
    domain: domain-id             # Target domain
    confidence: 0.0-1.0           # Routing confidence
    method: path|content          # Matching method
```

**Example:**
```yaml
routing_rules:
  # Path-based routing
  - pattern: "*/vulpine-solutions/*"
    domain: vulpine-solutions
    confidence: 0.95
    method: path

  - pattern: "*/homelab/*"
    domain: homelab
    confidence: 0.95
    method: path

  # Content-based routing (future)
  - pattern: "kubernetes|docker|container"
    domain: homelab
    confidence: 0.7
    method: content

  # Default fallback
  - pattern: "*"
    domain: general
    confidence: 0.5
    method: path
```

**Field Reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pattern` | string | Yes | Match pattern (glob for path, regex for content) |
| `domain` | string | Yes | Target domain ID (must exist in domains.yaml) |
| `confidence` | float | Yes | Routing confidence (0.0-1.0) |
| `method` | string | Yes | Matching method: `path` or `content` |

**Routing Priority:**
1. Explicit domain in frontmatter (highest priority)
2. Folder-based routing (`inbox/{domain}/file.md`)
3. Pattern-based routing (from routing.yaml)
4. Fallback to `general` domain

---

## `models.yaml`

**Source of Truth:** LLM provider configuration for extraction.

**Format:**
```yaml
default_provider: provider-name

providers:
  provider-name:
    api_key: ${ENV_VAR}         # API key from environment
    base_url: https://...       # API endpoint
    model: model-name           # Model identifier
    max_tokens: integer         # Max tokens per request
    temperature: 0.0-2.0        # Sampling temperature
```

**Example:**
```yaml
default_provider: openai

providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    model: gpt-4
    max_tokens: 4096
    temperature: 0.7

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    base_url: https://api.anthropic.com/v1
    model: claude-3-opus-20240229
    max_tokens: 4096
    temperature: 0.7
```

**Field Reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `default_provider` | string | Yes | Default provider to use |
| `providers` | object | Yes | Provider configurations |
| `api_key` | string | Yes | API key (use ${ENV_VAR} for environment variables) |
| `base_url` | string | Yes | API endpoint URL |
| `model` | string | Yes | Model identifier |
| `max_tokens` | integer | No | Maximum tokens per request |
| `temperature` | float | No | Sampling temperature (0.0-2.0) |

**Environment Variables:**
```bash
export OPENAI_API_KEY=your-key-here
export ANTHROPIC_API_KEY=your-key-here
```

**Note:** Current implementation does not use LLM extraction. This configuration is for future features.

---

## `daemon.yaml`

**Source of Truth:** Daemon job schedules and settings.

**Format:**
```yaml
daemon:
  check_interval: integer       # Seconds between daemon checks
  max_concurrent_jobs: integer  # Max parallel jobs
  log_level: INFO|DEBUG|WARNING # Log verbosity

jobs:
  job-name:
    enabled: boolean            # Whether job is enabled
    interval: integer           # Seconds between job runs
```

**Example:**
```yaml
daemon:
  check_interval: 60            # Check for work every 60 seconds
  max_concurrent_jobs: 3        # Run up to 3 jobs in parallel
  log_level: INFO               # Log level

jobs:
  inbox_watcher:
    enabled: true
    interval: 30                # Check inbox every 30 seconds

  index_rebuild:
    enabled: true
    interval: 3600              # Rebuild indexes every hour

  governance:
    enabled: true
    interval: 7200              # Run governance every 2 hours

  export:
    enabled: true
    interval: 3600              # Export every hour
```

**Field Reference:**

### Daemon Settings

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `check_interval` | integer | No | 60 | Seconds between daemon loop iterations |
| `max_concurrent_jobs` | integer | No | 3 | Maximum parallel jobs |
| `log_level` | string | No | INFO | Log verbosity (DEBUG, INFO, WARNING, ERROR) |

### Job Settings

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | boolean | No | true | Whether job is enabled |
| `interval` | integer | No | 3600 | Seconds between job executions |

**Available Jobs:**
- `inbox_watcher`: Monitor inbox for new files
- `index_rebuild`: Rebuild search indexes
- `governance`: Run governance checks
- `export`: Generate all exports

**Note:** Current daemon implementation is basic. See Issue #82 for planned scheduler enhancements.

---

## Configuration Validation

Configurations are validated at runtime using Pydantic models:

- `src/llm_wiki/models/domain.py`: Domain schema
- `src/llm_wiki/models/config.py`: Model provider schema
- `src/llm_wiki/models/routing.py`: Routing rules schema

**Validation checks:**
- Required fields present
- Correct field types
- Valid enum values
- Cross-references valid (e.g., domain IDs exist)

---

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENAI_API_KEY` | OpenAI API authentication | No (future feature) |
| `ANTHROPIC_API_KEY` | Anthropic API authentication | No (future feature) |

---

## Configuration Workflow

1. **Initial Setup:**
   ```bash
   # Edit domains
   vim config/domains.yaml

   # Initialize wiki structure
   uv run llm-wiki init
   ```

2. **Add Domain:**
   ```yaml
   # Add to domains.yaml
   - id: new-domain
     title: New Domain
     description: Description
     owners: [user]
     promote_to_shared: false
   ```

   ```bash
   # Recreate structure
   mkdir -p wiki_system/domains/new-domain/{pages,queue}
   ```

3. **Update Routing:**
   ```yaml
   # Add to routing.yaml
   - pattern: "*/new-domain/*"
     domain: new-domain
     confidence: 0.95
     method: path
   ```

4. **Validate:**
   ```bash
   # Test with sample file
   uv run llm-wiki ingest file test.md --domain new-domain
   ```

---

## Best Practices

1. **Keep domains stable:** Changing domain IDs breaks references
2. **Use semantic IDs:** Prefer descriptive domain names over abbreviations
3. **Start minimal:** Begin with 4-6 domains, not 20
4. **Document domains:** Use clear descriptions for each domain
5. **Review routing:** Regularly check that content routes correctly
6. **Secure API keys:** Never commit API keys to version control

---

## See Also

- [CLI.md](CLI.md) - Command-line interface
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SETUP.md](SETUP.md) - Installation and setup
