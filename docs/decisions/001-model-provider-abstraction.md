# Decision 001: Model Provider Abstraction

**Date**: 2026-04-13
**Status**: Accepted
**Context**: Issue #21

## Problem

The wiki system needs to call LLMs for extraction, integration, and lint operations. We need a provider abstraction that:
- Supports multiple LLM providers without hardcoding
- Survives model swaps without losing structure
- Is simple enough for v1 but extensible for future providers

## Decision

We will implement a **ModelClient abstract base class** with provider-specific implementations.

### Initial Implementation

**V1 Scope**: OpenAI-compatible API support only
- Providers: OpenAI, Ollama, LM Studio, generic local endpoints
- Uses standard OpenAI chat completions API format
- Single client implementation: `OpenAICompatibleClient`

**Deferred to later**:
- Anthropic Claude API (different message format)
- Streaming responses
- Function calling / tool use
- Provider-specific optimizations

### Interface Design

```python
class ModelClient(ABC):
    def chat_completion(
        messages: list[dict[str, str]],
        response_format: dict | None
    ) -> str

    def validate_config() -> None
```

**Why this interface:**
- Simple: Just messages in, string out
- Flexible: response_format allows JSON mode when needed
- Stateless: No session management needed
- Testable: Easy to mock

### Configuration

Models configured in `config/models.yaml` by purpose:
```yaml
models:
  extraction:
    provider: openai  # or ollama, lmstudio, local
    model: gpt-4
    temperature: 0.1
  integration:
    provider: openai
    model: gpt-4
    temperature: 0.1
```

### API Key Handling

- **OpenAI**: Requires `OPENAI_API_KEY` environment variable
- **Ollama/LM Studio/local**: No API key required (localhost)
- **Custom endpoints**: Optional `LLM_BASE_URL` environment variable

### Base URL Resolution

```
openai     -> https://api.openai.com/v1
ollama     -> http://localhost:11434/v1
lmstudio   -> http://localhost:1234/v1
local      -> $LLM_BASE_URL or http://localhost:8000/v1
```

### Error Handling

- All errors wrapped in `ModelClientError`
- Validation happens at client creation time
- Actual API calls will implement retry logic (future issue)

## Consequences

**Positive:**
- ✅ Easy to swap providers without code changes
- ✅ Works with local models (Ollama) for development
- ✅ Simple interface, hard to misuse
- ✅ Config-driven, no hardcoded assumptions

**Negative:**
- ⚠️ OpenAI-centric (but covers 80% of use cases)
- ⚠️ Adding Anthropic later requires new client class
- ⚠️ No streaming support (acceptable for v1)

**Trade-offs:**
- Chose simplicity over completeness
- Chose OpenAI compatibility over universal abstraction
- Can add more sophisticated clients later without breaking interface

## Alternatives Considered

### 1. Universal LLM library (e.g., LiteLLM)
- **Pros**: Supports all providers out of box
- **Cons**: Heavy dependency, less control, harder to debug
- **Decision**: Rejected for v1 - too much complexity

### 2. Provider-specific clients from day 1
- **Pros**: Optimal for each provider
- **Cons**: More code, more testing, delayed v1
- **Decision**: Rejected - YAGNI principle

### 3. No abstraction, direct API calls
- **Pros**: Simplest possible
- **Cons**: Hard to test, hard to swap providers
- **Decision**: Rejected - fails model swap requirement

## Implementation Notes

For Issue #21:
- ✅ Create abstract `ModelClient` base class
- ✅ Implement `OpenAICompatibleClient`
- ✅ Factory function `create_model_client()`
- ✅ Environment variable handling
- ⏭️ Actual API calls deferred to extraction issues (Epic 6)

The client returns NotImplementedError for `chat_completion()` until we add the openai package dependency in Epic 6.

## Future Evolution

**V2 additions:**
- Anthropic Claude client (`AnthropicClient`)
- Retry logic with exponential backoff
- Response caching
- Streaming for long outputs

**V3+ additions:**
- Function calling / tool use
- Multi-modal support
- Provider fallbacks
- Cost tracking
