# Data model

Postgres is the source of truth. Neo4j is a rebuildable projection. Symbols over
line numbers — `Grep` before editing.

## Current state

**Built — the Sprint 1 contract freeze has landed.** All 18 tables exist in
`api/db/models/` and are created by migration `0006`. `Document` is gone;
`Book` replaces it and `DocumentChunk` survives with `book_id`, `chapter_id`,
`token_count` and a generated `tsv`.

Enums live in `api/contracts/enums.py` and are stored as **native Postgres enum
types**. Adding a value is `ALTER TYPE … ADD VALUE` in a migration, not a code
change — worth knowing before you add a stage or a task type.

## Tables

| Table | Key columns | Status |
| --- | --- | --- |
| `user` | id, email (unique) | Built |
| `project` | id, name, slug, kind (`standalone`\|`series`) | S1 |
| `book` | id, **project_id, series_order**, title, author, content_hash **(unique)**, storage_key, page_count, chapter_count, status | S1/S2 |
| `chapter` | id, book_id, number, title, page_start, page_end, heading_text, detection_method, confidence, **human_verified** (0007) | S1/S2 |
| `documentchunk` | id, book_id, chapter_id, text, headings[], **pages[], page_start, page_end**, text_embedding `vector(1024)`, tsv, token_count | Built (v1 shape); reshaped S1 |
| `scene` / `scene_participant` | book_id, chapter_id, page range, chunk_ids[] / character_id | S4 |
| `dialogue_line` | chunk_id, char span, speaker_character_id, method, confidence | S4 |
| `character` | id, **project_id**, canonical_name, aliases[], importance_tier, first_book_id/first_chapter/first_page, last_*, mention_count, attributes, human_verified | **Built** (`api/extraction/repository.py::persist_characters`) |
| `character_appearance` | character_id × book_id: per-book first/last page+chapter, mention_count, tier, surface_forms[] | **Built** for a single book (S3); S5 is still the append target for a series |
| `character_mention` | id, character_id, **book_id**, chunk_id, surface_form, page, char span, confidence, resolution_method | **Built** |
| `book_character_candidate` | pass-1 staging before reconciliation | **Built** (S3.1/S3.2 write it; S5's `reconcile_characters` is still the reader that was meant to consume `resolved_character_id`) |
| `rejected_candidate` | surface_form, reason, contexts | **Built** |
| `relation` | id, **project_id**, subject_character_id, predicate, object_character_id, family, confidence, status, assertion_type, asserted_by, hearsay, human_verified, **first_book_order, first_chapter, last_book_order, last_chapter** | S4 |
| `relation_evidence` | id, relation_id **(FK cascade)**, **book_id, book_order**, chunk_id, page_start, page_end, chapter_no, quote, confidence | S4 |
| `reconciliation_decision` | book_id, cluster_key, character_id, method, confidence, blocked_by | S5 |
| `character_death` | character_id, book_id, chapter, evidence_id — the cross-book blocking signal | S5 |
| `ingestion_run` / `ingestion_stage` | book_id, stage, state, timings, attempt, error, tokens, cost | S2 |
| `review_task` | id, book_id, task_type, payload, graph_thread_id, priority, status, resolution | S7 for the queue UI/consumption; S3.4 already writes `merge_characters` rows on a blocked collision (`api/extraction/repository.py::queue_collision_review`) |
| `correction_feedback` | task_type, model_value, human_value, **model confidence at decision time**, evidence | S7 |
| `query_log` | question, route, retrieved ids, answer, citations, model, tokens, cost, latency_ms (jsonb), spoiler_chapter_limit, policy_version | S6/S9 |
| `eval_run` / `eval_result` | config (jsonb), corpus_version, git_sha, metrics | S8 |
| `routing_policy` / `cost_snapshot` | purpose → model, version | S9 |
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | LangGraph's own tables. **Not in Alembic** — created by `api.graph.checkpoint.setup_checkpointer()`, which owns their migrations. Do not autogenerate against them; Alembic will try to drop them. | Built |

## Constraints that carry meaning

| Constraint | Why |
| --- | --- |
| `book.content_hash` unique | Idempotent re-ingest (F1.5). Handle `IntegrityError`; do not check-then-insert. |
| `documentchunk` page range NOT NULL | Page provenance is mandatory (F1.3). Enforced in the DB, not by convention. |
| `character (project_id, canonical_name)` unique | **Project-scoped: one Harry Potter, not seven.** A standalone book is a one-book project — there is no second code path. |
| `character_appearance (character_id, book_id)` unique | The per-book append target (F2.5) |
| `book (project_id, series_order)` unique | Series ordering, user-set, nullable for standalone |
| `relation (subject, predicate, object, first_book_order, first_chapter)` unique | The aggregation key (F3.5), in **series position** — one edge with evidence from every book that establishes it |
| `relation_evidence.relation_id` ON DELETE CASCADE | Evidence cannot outlive its edge |
| ivfflat on `text_embedding` (`vector_cosine_ops`) | Similarity search; embeddings **must** be normalised or distances are wrong |
| GIN on `tsv` | BM25 arm of hybrid retrieval |

## Invariants

- **`human_verified` is never overwritten.** Enforced at the repository layer,
  not per call site. A re-run that disagrees creates a review task.
- **Every relation has ≥1 evidence row.** `graph.upsert` raises otherwise.
- **Temporal change closes an edge** (`last_book_order`/`last_chapter`,
  `status='superseded'`) and opens a new one. Never an UPDATE of the predicate.
- **Validity is series position `(book_order, chapter)`**, compared with SQL row
  comparison: `(r.first_book_order, r.first_chapter) <= (:b, :c)`. A standalone
  is `(1, chapter)`.
- **Derived character fields are recomputed from all appearances**, never
  accumulated — that is what makes out-of-order series ingestion self-correct.
- Neo4j holds no fact absent from Postgres. `make graph-rebuild` re-projects.

## Migrations

**One migration per sprint, authored by the orchestrator at the contract
freeze.** Agents never write migrations — two agents writing `0006` produces a
branch Alembic refuses to run. Need a column? File an SCR (BRANCH.md §8).

**Current head: `0007`** — `0006` was the full v2 schema; `0007` (Sprint 2
freeze) added `chapter.human_verified` (SCR-1 — chapters needed the same
human-verified guard `character` and `relation` already carry, for S7's
`confirm_chapter_split`). Later sprints add only what their behaviour needs.

Both are verified reversible: `head → 0005 → head → base → head` (0006), and a
no-op `autogenerate` reports zero drift after 0007. `0006`'s downgrade restores
**structure, not data** — it truncates v1 chunks and drops `document`, and
says so.

**LangGraph's checkpointer tables are excluded from autogenerate entirely**
(`api/db/migrations/env.py::include_object`) — `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` are created by
`api/graph/checkpoint.py::setup_checkpointer()`, not Alembic, and without the
filter every single `autogenerate` proposes dropping them. Nearly shipped as
part of `0007`; excluded at the source now instead.
