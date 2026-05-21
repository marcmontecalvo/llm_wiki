# Story 2.4: Vector Search Integration

Status: pending

## Story

As a user of the wiki search system,
I get semantically relevant results from vector search merged with full-text and metadata search,
So that I find the right pages even when my query doesn't use the exact terminology (FR45).

## Acceptance Criteria

1. **Given** vector search is requested **When** results are merged with full-text via RRF **Then** pages appear in results when either semantic or keyword matching is satisfied.

2. **Given** vector search results are returned **When** the page has metadata **Then** the result includes `confidence` computed from the page's trust tags and `score` from vector similarity.

3. **Given** the FAISS vector index exists on disk **When** the service starts **Then** it is loaded into memory for lookup at startup.

4. **Given** a new page is added **When** the page is committed **Then** it is indexed in the FAISS vector store with its embedding.

5. **Given** pages are modified **When** rebuild is triggered **Then** all vectors are recomputed from page content and the index is atomically replaced.

## Tasks / Subtasks

- [x] Task 1: Ensure vector search includes confidence in results (AC: 2)
  - [x] 1.1 Vector search `search()` already returns `{page_id, title, domain, score}` — add confidence lookup
  - [x] 1.2 Vector search uses doc_meta to find frontmatter fields
  - [x] 1.3 Vector search does NOT read full frontmatter at search time — rely on pre-computed metadata stored in `doc_meta`
  - [x] 1.4 The search() method already merges RRF from both sources — verified

- [x] Task 2: Verify vector search loads at startup (AC: 3, 4)
  - [x] 2.1 WikiQuery._load_indexes() loads metadata + fulltext + vector
  - [x] 2.2 VectorIndex.load() reads vector_meta.json and vector_index.faiss
  - [x] 2.3 VectorIndex.add_document() embeds and stores vector
  - [x] 2.4 WikiQuery.add_page() calls vector_index.add_document() — verified

- [x] Task 3: Verify rebuild from pages atomsically replaces index (AC: 5)
  - [x] 3.1 VectorIndex.save() uses tmp + os.replace — verified
  - [x] 3.2 WikiQuery.rebuild_indexes() calls vector_index.rebuild_from_pages() — verified

## Dev Notes

### Key Files
- `src/llm_wiki/index/vector.py` — Already has FAISS integration with _ensure_model, _load_faiss_index, add_document, search, save, rebuild_from_pages
- `src/llm_wiki/query/search.py` — RRF merge of fulltext + vector
- `src/llm_wiki/api/routers/search.py` — Search endpoint

### Architecture Notes
- Vector index uses `all-MiniLM-L6-v2` from sentence-transformers
- FAISS `IndexFlatL2` with normalized embeddings → cosine distance via L2
- Index stored as `vector_index.faiss` + `vector_meta.json`
- Vector search is always active — no feature flag
- Embedding computed on `title + content` with markdown stripped

### What NOT to change
- No changes to FAISS index format
- No changes to RRF constant (60)
- No new dependency on LLM service

### Testing
- Verify vector index loads from disk when pages exist
- Verify new pages get vectors after add_document + save
- Verify rebuild replaces index atomically
