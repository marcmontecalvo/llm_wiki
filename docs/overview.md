# Overview

## Core architecture

This repo is for a **federated wiki system**.

That means:
- one runtime
- one daemon
- one shared search/index layer
- many bounded domains
- one shared graph for cross-domain linking

## Why not one flat wiki

Because it will rot.

If Vulpine, Home Assistant, woodworking, pool care, and random experiments all live in one undifferentiated namespace, then:
- routing gets noisy
- pages get bloated
- maintenance cost goes up
- the agent over-links unrelated topics
- confidence drops over time

## Why not many isolated wikis

Because it duplicates concepts and kills reuse.

You will absolutely have overlap between domains:
- networking concepts
- automation patterns
- vendors and products
- project management patterns
- home automation components that also touch homelab or pool automation

## Best middle ground

Use this model:
- **domain-local pages first**
- **shared concept/entity pages only when justified**
- **cross-domain links allowed but explicit**
- **default traversal stays domain-scoped first**

## What we are stealing from each repo

### Labhund/llm-wiki
Use for:
- daemon concept
- background maintenance loop
- MCP-facing service design
- operational honesty checks
- index/lint/audit mindset

Do not copy blindly:
- single-domain assumptions
- direct production assumptions, because the repo explicitly warns it is still under active development

Repo:
https://github.com/Labhund/llm-wiki

### nvk/llm-wiki
Use for:
- project/wiki partitioning
- portable agent conventions
- wiki workflow shape
- scoped topic wiki thinking

Do not copy blindly:
- anything that assumes the agent itself is enough to enforce state

Repo:
https://github.com/nvk/llm-wiki

### Pratiyush/llm-wiki
Use for:
- adapter strategy
- transcript/session import paths
- static export targets
- AI-readable output formats
- sidecar file discipline

Do not copy blindly:
- assumptions that transcript history is the main source of truth

Repo:
https://github.com/Pratiyush/llm-wiki

### Ar9av/obsidian-wiki
Use for:
- cross-agent setup patterns
- symlink/bootstrap logic
- broad compatibility mindset

Do not copy blindly:
- skill-only operational assumptions

Repo:
https://github.com/Ar9av/obsidian-wiki

### Later repos

#### nashsu/llm_wiki
Use later for:
- graph UX ideas
- richer browsing UX
- product polish ideas

https://github.com/nashsu/llm_wiki

#### lucasastorian/llmwiki
Use later for:
- heavier web app structure
- separate API/frontend patterns
- auth if needed later

https://github.com/lucasastorian/llmwiki

#### kenhuangus/llm-wiki
Use only for:
- research agenda patterns
- metrics/eval ideas
- security taxonomy ideas

https://github.com/kenhuangus/llm-wiki

## Final architecture decision

**Base = Labhund + NVK**

**V1 add-in = Pratiyush**

**Optional V1 helper = Ar9av**

**V4 inspiration = nashsu, maybe lucasastorian**
