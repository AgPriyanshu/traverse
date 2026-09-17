# Sprint 1 — Foundations & Contracts

**Goal:** a cold `docker compose up` brings the entire stack green, the v2 data
model is migrated, every cross-agent contract is frozen, and the web shell
renders real (empty) data from the real API.

**Why this sprint exists.** Nothing here is user-visible, and that is the point.
Sprints 2–8 run four agents in parallel; they can only do that if the schema,
the API shape, the task names, and the container topology are settled first.
Every hour skipped here is repaid with interest in merge conflicts.

**PRD refs:** Phase 0, Phase 1.5 · NFR-deploy, NFR-obs

---

## Contract freeze (Day 1, orchestrator, on `ai-master`) — ✅ LANDED

Delivered on `ai/orchestrator/sprint-1-freeze`: 18 tables, migration `0006`
(verified reversible), `api/contracts/` with 65 models, 33 frozen route stubs
carrying real response models, the frozen Celery task-name registry, and the
expanded settings. `ruff check` and `ruff format --check` are clean.

This is the largest freeze of the project. Everything below lands before any
worktree branch is cut.

### 1. Data model — `api/db/models/`

Replace the v1 `Document`/`DocumentChunk` model with the PRD §5.5 schema.
**Project-scoped from the first migration** — see below:

```
project_model.py    Project, Book, Chapter
chunk_model.py      DocumentChunk           (rewrite: + book_id, chapter_id, token_count, tsv)
character_model.py  Character, CharacterAppearance, CharacterMention,
                    BookCharacterCandidate
relation_model.py   Relation, RelationEvidence
review_model.py     ReviewTask
ops_model.py        QueryLog, EvalRun, IngestionRun, IngestionStage
```

**Why project-scoped now, when series support is Sprint 5.** A project holds one
standalone novel or an ordered series; `character` and `relation` are keyed on
`project_id`, not `book_id`. Adding that now costs one extra column and one
extra table. Adding it after Sprint 4 means re-migrating every character,
relation, and evidence row *and* rebuilding the Neo4j projection — a sprint of
rework to reach the same schema. Through Sprints 2–4 every project simply has one
book, so nothing else changes.

Every model uses `UUID` primary keys, `created_at`/`updated_at`, and — where the
PRD calls for it — `human_verified: bool` defaulting to `False`.

### 2. Migration — `api/db/migrations/versions/0006_v2_schema.py`

**One migration. Authored by the orchestrator. No agent writes migrations.**
Drops `documentchunk.document_id` in favour of `book_id`, creates all new
tables, and adds:

- `ivfflat` index on `documentchunk.text_embedding` (`vector_cosine_ops`)
- GIN index on `documentchunk.tsv` for the BM25 path
- unique `(project_id, canonical_name)` on `character`
- unique `(character_id, book_id)` on `character_appearance` — the per-book
  append target (F2.5)
- unique `(project_id, series_order)` on `book` where `series_order` is not null
- unique `(subject_character_id, predicate, object_character_id,
  first_book_order, first_chapter)` on `relation` — the aggregation key from
  F3.5, in **series position**
- FK `relation_evidence.relation_id` → `relation.id` **ON DELETE CASCADE**

### 3. Contracts — `api/contracts/`

Pydantic models shared across agent boundaries. Agents import these; they never
edit them.

```python
# api/contracts/pipeline.py
class ChapterInfo(BaseModel):
    is_chapter: bool
    number: int | None = None
    title: str | None = None
    text: str | None = None
    detection_method: Literal["regex", "llm", "manual"]

class ChunkPayload(BaseModel):
    text: str
    text_embedding: list[float]
    pages: list[int]
    page_start: int
    page_end: int
    chapter_number: int | None
    token_count: int

class StageStatus(BaseModel):
    stage: StageName          # enum, see task registry below
    state: Literal["pending", "running", "succeeded", "failed", "skipped"]
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    attempt: int
```

```python
# api/contracts/extraction.py
class CharacterCandidate(BaseModel):
    surface_form: str
    chunk_id: UUID
    page: int
    chapter_number: int | None
    context: str                      # ±1 sentence, for the resolver
    kind: Literal["person", "place", "org", "unknown"]

class ResolvedCharacter(BaseModel):
    canonical_name: str
    aliases: list[str]
    mention_ids: list[UUID]
    importance_tier: Literal["protagonist", "major", "minor", "mentioned"]
    first_page: int
    first_chapter: int | None
    mention_count: int

class SeriesPosition(BaseModel):
    book_order: int          # 1 for a standalone — one code path, no branching
    chapter: int | None
```

```python
# api/contracts/graph.py
class ExtractedRelation(BaseModel):
    subject_name: str                 # MUST match a Character.canonical_name
    predicate: Predicate              # enum from the ontology config
    object_name: str
    assertion_type: Literal["narrated", "dialogue", "inferred"]
    asserted_by: str | None
    quote: str = Field(max_length=400)    # ETH-3 quote cap
    chunk_id: UUID
    confidence: float = Field(ge=0.0, le=1.0)
```

```python
# api/contracts/api.py   — HTTP response models, the FE1 contract
BookOut, BookStatusOut, ChapterOut, ChunkOut
CharacterOut, CharacterDetailOut, MentionOut
GraphOut (nodes, edges), RelationOut, EvidenceOut
QueryRequest, QueryEvent (SSE discriminated union), CitationOut
ReviewTaskOut, ReviewResolution
```

### 4. Route stubs — `api/routes/`

```
__init__.py        router registry — orchestrator-owned, all includes wired
books.py           be1        stubs raise HTTPException(501)
characters.py      be2
graph.py           be2
query.py           be2
review.py          be2
ops.py             do1
```

Every stub carries its final `response_model`, so `/openapi.json` is correct and
complete on Day 1 and FE1 can generate a typed client immediately.

### 5. Celery task-name registry — `api/tasks.py`

**The key decoupling of the whole project.** The chain is declared with Celery
*string* signatures, so BE2's tasks are referenced by name and BE2 never edits
BE1's file:

```python
STAGES = [
    "pipeline.parse_and_chunk",     # be1
    "pipeline.segment_chapters",    # be1
    "pipeline.embed_chunks",        # be1
    "pipeline.extract_characters",  # be1
    "pipeline.resolve_aliases",     # be1
    "relations.extract",            # be2
    "relations.aggregate",          # be2
    "graph.upsert",                 # be2
]

def ingestion_chain(book_id: UUID) -> Signature:
    return chain(*[
        celery_app.signature(name, args=(str(book_id),), immutable=True)
        for name in STAGES
    ])
```

Each agent registers its own tasks under its own module with
`@celery_app.task(name="pipeline.embed_chunks", bind=True, autoretry_for=...)`.
Task **names** are frozen; implementations are not.

### 6. Settings — `api/config/settings.py`

Add: `neo4j_uri`, `neo4j_user`, `neo4j_password`, `rabbitmq_url`,
`minio_endpoint`/`access_key`/`secret_key`/`bucket`, `vllm_base_url`,
`llm_model`, `embedding_model_id`, `embedding_device`, `docling_cache_dir`,
`api_port`, `inference_mode` (`local` | `api` | `routed`).

**Kill every hardcoded absolute path.** `CACHE_DIR` in `chunking.py` is
currently `/home/prinzz/main/my-projects/traverse/api/.cache/` — this breaks
inside every container and is a Sprint 1 blocker, not a nit.

---

## Sprint scope

| Story | Owner | Summary |
|---|---|---|
| S1.1 | be1 | Celery worker bootstrap, warm-up, task registration, stage-status recorder |
| S1.2 | be1 | Config-driven chunker — no hardcoded paths, injectable device and cache |
| S1.3 | be1 | Repository layer for Book / Chapter / DocumentChunk |
| S1.4 | be2 | Neo4j async driver lifecycle, constraints, indexes, `graph.reset()` |
| S1.5 | be2 | Ontology config module — predicates, families, inverses, symmetry |
| S1.6 | be2 | LangGraph Postgres checkpointer wired and restart-verified |
| S1.7 | be2 | Read APIs backed by real (empty) tables — characters, graph, books |
| S1.8 | fe1 | App shell — routing, Chakra theme, layout, dark mode, error boundaries |
| S1.9 | fe1 | Typed API client generated from `/openapi.json` + TanStack Query setup |
| S1.10 | fe1 | Book list and upload page against the real API |
| S1.11 | do1 | RabbitMQ, Celery worker, MinIO, Langfuse as compose services |
| S1.12 | do1 | API + web Dockerfiles, healthchecks, `depends_on: service_healthy` |
| S1.13 | do1 | Makefile, `.env.example`, migration runner, per-agent DB bootstrap |
| S1.14 | do1 | CI: ruff + oxlint + pytest + `tsc --noEmit` on every PR |
| S1.15 | do1 | Model cache warm-up (Docling + BGE-M3) baked or volume-mounted |

---

## Demo script (Day 5)

Run on the integration checkout, from a cold machine state.

```bash
git clean -xfd && docker compose down -v
cp .env.example .env
make up                                   # < 5 min to all-healthy on a warm cache
docker compose ps                         # every service healthy, none restarting
curl -s localhost:8000/health | jq        # {"status":"ok","db":"ok","neo4j":"ok","broker":"ok","llm":"ok"}
curl -s localhost:8000/openapi.json | jq '.paths | keys | length'   # ≥ 18
make migrate && make seed-empty
open http://localhost:5174                # shell renders, nav works, dark mode toggles,
                                          # book list shows the real empty state from the API
make test                                 # backend + frontend green
docker compose logs celery-worker | grep "ready"
```

Then kill the worker mid-task and confirm the LangGraph checkpointer resumes
(S1.6) — this is the one behavioural test in an otherwise structural sprint,
and it is here because discovering it broken in Sprint 7 is expensive.

## Definition of Done

- [ ] All 15 stories merged via the merge train
- [ ] Demo script runs clean on a machine that has never built the project
- [ ] `/openapi.json` complete — every Sprint 2–8 endpoint present as a stub
- [ ] Zero hardcoded absolute paths anywhere in `api/`
- [ ] CI green on `ai-master`
- [ ] `HANDOFF.md` records the frozen task names and contract module paths
- [ ] `RETRO.md` written
