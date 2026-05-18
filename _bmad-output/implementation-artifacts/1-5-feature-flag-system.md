# Story 1.5: Feature Flag System

Status: ready-for-dev

## Story

As an operator,
I want a feature flag system in `daemon.yaml` to enable or disable optional capabilities,
so that the service works fully without any LLM dependency by default and new capabilities can be enabled and tested independently.

**Prerequisite:** Story 1.4 must be complete — feature flags are loaded in the FastAPI lifespan and are required before any endpoint code is written.

## Acceptance Criteria

1. **Given** `daemon.yaml` contains a `features:` block **When** the service starts **Then** `WikiConfig` loads and validates all flags; unknown flags are rejected at startup with a clear error.

2. **Given** `features.llm_extraction: false` (default) **When** any extraction pipeline step runs **Then** it uses heuristic fallbacks (TF-IDF tags, first-paragraph summary, skip claims) — no LLM client is instantiated, no `models.yaml` is required.

3. **Given** `features.llm_extraction: true` **When** the service starts **Then** it reads `models.yaml`, validates the provider config, and instantiates the LLM client; startup fails with a clear error if `models.yaml` is missing or the provider config is invalid.

4. **Given** `features.synthesis_cache: false` or `features.cross_domain_promotion: false` **When** the daemon scheduler initializes **Then** the corresponding jobs are not registered and cannot be triggered manually.

5. **Given** `features.lazy_vector_load: false` (default) **When** the service starts **Then** the FAISS index loads immediately in the FastAPI lifespan — vector search is available from first request.

6. **Given** `features.lazy_vector_load: true` **When** the service starts **Then** the FAISS index is not loaded during lifespan; it loads on the first search call; cold start is faster but the first search pays the load cost.

7. **Given** any health or status response **When** returned **Then** it includes `llm_extraction_enabled: bool` capability indicator. There is no `vector_search_enabled` field — vector search is always on and FAISS is a required dependency.

## Tasks / Subtasks

- [ ] Add `FeaturesConfig` model to `src/llm_wiki/models/config.py` (AC: 1)
  - [ ] `llm_extraction: bool = False`
  - [ ] `synthesis_cache: bool = False`
  - [ ] `cross_domain_promotion: bool = False`
  - [ ] `lazy_vector_load: bool = False`
  - [ ] **No `vector_search` flag** — FAISS is a required dependency; remove any existing `vector_search` field
  - [ ] Validator: reject extra/unknown fields (use `model_config = ConfigDict(extra="forbid")`)
- [ ] Add `features: FeaturesConfig` field to `DaemonConfig` (AC: 1)
- [ ] Update `config/daemon.yaml` example to include `features:` block with defaults (AC: 1)
- [ ] Move FAISS from optional extra to required dependency in `pyproject.toml` (AC: 1)
  - [ ] Remove `[project.optional-dependencies] vector = ["faiss-cpu"]` section
  - [ ] Add `faiss-cpu` to base `[project.dependencies]`
  - [ ] Update Dockerfile: change `uv sync --frozen --extra vector` → `uv sync --frozen`
- [ ] Wire `llm_extraction` flag into extraction pipeline (AC: 2, 3)
  - [ ] Update `src/llm_wiki/extraction/enrichment.py` (or `pipeline.py`) to check `features.llm_extraction`
  - [ ] When `False`: use TF-IDF for tags, first-paragraph for summary, skip LLM claims
  - [ ] When `True`: validate `models.yaml` is present and provider config is valid at startup; raise `ConfigError` if not
- [ ] Wire `synthesis_cache` and `cross_domain_promotion` flags into daemon job registration (AC: 4)
  - [ ] In `WikiDaemon.start()`: gate `SynthesisCacheJob` and `PromotionJob` registrations behind these flags
  - [ ] If flag is False, the job is not added to the scheduler
- [ ] Wire `lazy_vector_load` into FastAPI lifespan and `WikiQuery` (AC: 5, 6)
  - [ ] When `False`: load FAISS in lifespan (current behavior)
  - [ ] When `True`: skip FAISS load in lifespan; load on first `VectorIndex.search()` call
- [ ] Surface capability indicator in health/status responses (AC: 7)
  - [ ] `HealthResponse` (from Story 1.4's models.py): add `llm_extraction_enabled: bool`
  - [ ] **Remove `vector_search_enabled`** from `HealthResponse` — vector search is always on
  - [ ] Populate from `app.state.wiki.config.features.llm_extraction`

## Dev Notes

### Current State — What Needs to Change

**`src/llm_wiki/models/config.py`** — `DaemonConfig` has no `features` field. `ModelsYAML` loading is optional (currently only read if `models.yaml` exists). After this story, `models.yaml` is only required when `features.llm_extraction: true`.

**`src/llm_wiki/config/loader.py`** — Read this file before implementing to understand how configs are loaded. The feature flag validation must integrate with the existing load path. `models.yaml` may currently be required — this story makes it optional.

**`src/llm_wiki/extraction/`** — The extraction pipeline (`enrichment.py` or `pipeline.py`) currently assumes LLM calls are available. This story adds the heuristic fallback path.

### FeaturesConfig Pydantic Model

```python
# src/llm_wiki/models/config.py — add before DaemonConfig
from pydantic import ConfigDict

class FeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unknown flags at startup

    llm_extraction: bool = False
    synthesis_cache: bool = False
    cross_domain_promotion: bool = False
    lazy_vector_load: bool = False
    # vector_search is NOT a flag — FAISS is a required dependency, always enabled


# In DaemonConfig:
class DaemonConfig(BaseModel):
    ...
    features: FeaturesConfig = Field(
        default_factory=FeaturesConfig, description="Feature flags"
    )
```

### `models.yaml` Conditional Loading

```python
# src/llm_wiki/config/loader.py — make models.yaml optional
def load_config(config_dir: Path) -> WikiConfig:
    daemon_config = load_daemon_config(config_dir / "daemon.yaml")
    domains_config = load_domains_config(config_dir / "domains.yaml")
    routing_config = load_routing_config(config_dir / "routing.yaml")

    # models.yaml only required when llm_extraction: true
    models_config = None
    models_path = config_dir / "models.yaml"
    if daemon_config.daemon.features.llm_extraction:
        if not models_path.exists():
            raise ConfigError(
                "features.llm_extraction is true but models.yaml not found at "
                f"{models_path}. Create models.yaml with provider config."
            )
        models_config = load_models_config(models_path)
    elif models_path.exists():
        # Load it anyway if present, but don't require it
        models_config = load_models_config(models_path)

    return WikiConfig(
        domains=domains_config,
        daemon=daemon_config,
        routing=routing_config,
        models=models_config,
    )
```

### Extraction Fallback — Heuristic Path

```python
# src/llm_wiki/extraction/enrichment.py (or pipeline.py)
def get_tags_heuristic(content: str, max_tags: int = 5) -> list[str]:
    """TF-IDF approximation: top N words by frequency, excluding stopwords."""
    # Simple word frequency (no external library needed)
    import re
    words = re.findall(r'\b[a-z]{4,}\b', content.lower())
    stopwords = {"this", "that", "with", "from", "have", "will", "they", "been", ...}
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda k: freq[k], reverse=True)[:max_tags]

def get_summary_heuristic(content: str, max_chars: int = 200) -> str:
    """First non-heading paragraph, truncated."""
    import re
    paras = re.split(r'\n\n+', content)
    for para in paras:
        stripped = para.strip()
        if stripped and not stripped.startswith('#'):
            return stripped[:max_chars]
    return content[:max_chars]
```

### daemon.yaml Example

```yaml
# config/daemon.yaml
daemon:
  inbox_poll_seconds: 15
  rebuild_index_every_minutes: 30
  export_every_minutes: 60
  lint_every_minutes: 60

  features:
    llm_extraction: false      # set true to enable LLM tagging/summarization
    synthesis_cache: false     # Sprint 3
    cross_domain_promotion: false  # Sprint 3
    lazy_vector_load: false    # set true if cold start >30s
    # vector search is always enabled — FAISS is a required dependency
```

### Daemon Job Gating

```python
# src/llm_wiki/daemon/main.py — in WikiDaemon.start()
features = self.config.daemon.daemon.features  # FeaturesConfig

# Gate synthesis cache job (Sprint 3)
if features.synthesis_cache:
    from llm_wiki.daemon.jobs.synthesis_cache import run_synthesis_cache
    self.scheduler.add_job(func=run_synthesis_cache, ...)

# Gate promotion job (already gated, add feature flag check)
if self.config.daemon.daemon.promotion.enabled and features.cross_domain_promotion:
    from llm_wiki.daemon.jobs.promotion import run_promotion_check
    self.scheduler.add_job(func=run_promotion_check, ...)
```

### Project Structure — Files to Modify

```
src/llm_wiki/
├── models/config.py           UPDATE — add FeaturesConfig, features field in DaemonConfig
├── config/loader.py           UPDATE — make models.yaml conditional on llm_extraction flag
├── extraction/enrichment.py   UPDATE — add heuristic fallback path
├── extraction/pipeline.py     UPDATE — check llm_extraction flag before LLM calls
├── query/search.py            UPDATE — check vector_search flag in search()
└── daemon/main.py             UPDATE — gate synthesis_cache and cross_domain_promotion jobs

config/
└── daemon.yaml                UPDATE — add features: block
```

### Testing

`tests/unit/test_features_config.py` (new):

```python
def test_features_default_flags():
    cfg = FeaturesConfig()
    assert cfg.llm_extraction is False
    assert cfg.vector_search is True
    assert cfg.lazy_vector_load is False

def test_features_rejects_unknown_flags():
    with pytest.raises(ValidationError):
        FeaturesConfig(unknown_flag=True)

def test_models_yaml_required_when_llm_extraction_true(tmp_path):
    """No models.yaml raises ConfigError when llm_extraction: true."""
    daemon_yaml = tmp_path / "daemon.yaml"
    daemon_yaml.write_text("daemon:\n  features:\n    llm_extraction: true\n")
    with pytest.raises(ConfigError, match="models.yaml"):
        load_config(tmp_path)
```

### Critical Anti-Patterns to Avoid

- **Do not** use bare `extra = "allow"` on FeaturesConfig — unknown flags must fail at startup so operators know they have a typo
- **Do not** instantiate LLMClient when `features.llm_extraction: false`
- **Do not** load FAISS in lifespan when `features.lazy_vector_load: true`
- **Do not** register `SynthesisCacheJob` when `features.synthesis_cache: false` — it must not be triggerable

### References

- Architecture: "Feature Flags" — complete `daemon.yaml` and `models.yaml` patterns
- `src/llm_wiki/models/config.py:99-150` — existing `DaemonConfig` to extend
- `src/llm_wiki/config/loader.py` — read before implementing config changes
- `src/llm_wiki/extraction/enrichment.py` — read before implementing heuristic fallback

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
