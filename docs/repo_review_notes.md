# Repo Review Notes

These are the short takeaways that drove this plan.

## Labhund/llm-wiki
Why it is in:
- best daemon/governance center of gravity
- agent-first design
- plain markdown + MCP + maintenance loop is the right direction

Why not use it raw as-is:
- README explicitly warns it is still under active development and not recommended for production use
- appears shaped around a narrower topic domain than the long-term system here needs

Repo:
https://github.com/Labhund/llm-wiki

## nvk/llm-wiki
Why it is in:
- best project/topic partitioning model
- portable agent workflow shape
- strong fit for federated topic wikis

Notable signal:
- there is already an issue discussing auto-routing across topic wikis, which validates the same scaling concern you raised

Repo:
https://github.com/nvk/llm-wiki

## Pratiyush/llm-wiki
Why it is in:
- best session transcript adapter design
- best machine-readable export direction for v1
- actively thinking about review, synthesis, and packaging

Repo:
https://github.com/Pratiyush/llm-wiki

## Ar9av/obsidian-wiki
Why it is maybe-in:
- very good cross-agent bootstrap layer
- strong compatibility mindset
- useful if you want the same wiki conventions exposed to multiple coding agents

Repo:
https://github.com/Ar9av/obsidian-wiki

## nashsu/llm_wiki
Why it is later-only:
- strongest product/UI/graph inspiration
- wrong center of gravity for base architecture

Repo:
https://github.com/nashsu/llm_wiki

## lucasastorian/llmwiki
Why it is later-only:
- heavier web app shell
- useful later if you want a more app-like surface
- not needed for v1 correctness

Repo:
https://github.com/lucasastorian/llmwiki

## kenhuangus/llm-wiki
Why it is not core:
- smart repo, but too specialized
- useful only for metrics/eval/research-agenda ideas

Repo:
https://github.com/kenhuangus/llm-wiki
