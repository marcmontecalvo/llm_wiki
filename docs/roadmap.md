# Roadmap

## V0 - repo scaffold

Goal:
- create the base repo, folder structure, contracts, and design docs

Deliverables:
- base repo skeleton
- domain config
- daemon config
- page templates
- implementation steps

## V1 - daemonized local wiki core

Goal:
- build a reliable local daemon that manages a federated wiki

Must-have:
- inbox watcher
- domain router
- markdown normalizer
- extraction contracts
- integration pipeline
- shared metadata index
- basic fulltext search
- append-only operations log
- scheduled lint/index jobs
- transcript + markdown adapters
- exports: `llms.txt`, JSON sidecars, simple graph export

Borrow from:
- Labhund
- NVK
- Pratiyush

Exit criteria:
- can ingest new source docs without manual repo surgery
- can keep 4-6 domains clean
- can rebuild index deterministically
- can survive model swaps with acceptable drift

## V2 - trust and review layer

Goal:
- make the wiki safer to trust

Must-have:
- candidate pages / approval flow
- contradiction detector
- stale-page detector
- confidence fields
- source citation enforcement
- orphan page checks

Borrow from:
- Labhund governance ideas
- Pratiyush candidate/review direction
- kenhuangus metrics/eval ideas

Exit criteria:
- hallucinated page creation is contained
- stale claims are surfaced automatically
- low-confidence content is visible and reviewable

## V3 - richer cross-domain synthesis

Goal:
- allow useful shared knowledge without flattening all domains

Must-have:
- shared concept/entity promotion flow
- cross-domain summary pages
- per-domain and global dashboards
- better ranking and traversal heuristics

Borrow from:
- NVK topic scoping
- kenhuangus synthesis/eval discipline

Exit criteria:
- shared pages are high-signal, not clutter
- cross-domain navigation helps more than it hurts

## V4 - UX + product layer

Goal:
- make the system pleasant to browse and operate

Must-have:
- graph view
- better query UI
- browse by entity/concept/source
- daemon control panel
- richer site generation

Borrow from:
- nashsu UI/graph ideas
- lucasastorian app-shell ideas

Exit criteria:
- useful to humans, not just agents

## V5 - optional online integrations

Goal:
- selectively add remote inputs without losing local-first discipline

Possible additions:
- GitHub repo ingestion
- docs site ingestion
- RSS feeds
- optional cloud sync

Hard rule:
- remote ingestion is optional, not required for core correctness
