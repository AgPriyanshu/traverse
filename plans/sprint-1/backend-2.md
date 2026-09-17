# Sprint 1 · Backend Engineer 2

**Branch:** `ai/be2/sprint-1-foundations` · **Worktree:** `../traverse-wt/be2`
**Read first:** [BRANCH.md](../../BRANCH.md), [sprint-1/README.md](README.md)

## Mission

Stand up the graph and agent substrate. Neo4j currently exists as a compose
service and a 12-line stub with a `CREATE` query that was never finished. By the
end of this sprint the graph store has a real lifecycle, a declared ontology, a
rebuildable schema, and the LangGraph Postgres checkpointer is proven to survive
a process restart. No relationship extraction yet — that is Sprint 4.

## Owned paths

```
api/graph/**  api/relations/**  api/query/**
api/routes/characters.py  api/routes/graph.py  api/routes/query.py  api/routes/review.py
api/tests/graph/**  api/tests/query/**
```

Forbidden: `api/pipeline/**`, `api/extraction/**`, `api/db/models/**`,
`api/db/migrations/**`, `api/contracts/**`, `web/**`, `docker-compose.yml`.

**You have exclusive write access to Neo4j** (Community edition is
single-database — BRANCH.md §9). Nobody else touches it until integration.

## Setup

```bash
cd ../traverse-wt/be2/api && uv sync
cat > .env <<'EOF'
POSTGRES_DB_STRING=postgresql+psycopg://postgres:postgres@localhost:5433/traverse_be2
NEO4J_URI=neo4j://localhost:7687
NEO4J_PASSWORD=very_safe_password
RABBITMQ_URL=pyamqp://guest:guest@localhost:5672/be2
EMBEDDING_DEVICE=cpu
API_PORT=8002
EOF
uv run alembic upgrade head
```

---

## S1.4 — Neo4j driver lifecycle

Replace `api/db/graph_db.py`'s stub with `api/graph/client.py`:

- **One long-lived `AsyncDriver` for the process**, created on FastAPI startup
  and on `worker_process_init`, closed on shutdown. The current code creates a
  driver per call inside an `asynccontextmanager` — that opens a fresh
  connection pool per query and will collapse under the Sprint 4 upsert load.
- Credentials from settings, never literals.
- `session()` helper yielding a driver session with the database name from
  config.
- `healthcheck()` returning driver connectivity for DO1's `/health`.
- Retry on `ServiceUnavailable` with backoff — Neo4j takes ~20s to accept
  connections after container start, and every agent will hit this.

**Schema bootstrap**, idempotent, run at startup:

```cypher
CREATE CONSTRAINT character_id IF NOT EXISTS
  FOR (c:Character) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT book_id IF NOT EXISTS
  FOR (b:Book) REQUIRE b.id IS UNIQUE;
CREATE INDEX character_book IF NOT EXISTS FOR (c:Character) ON (c.book_id);
CREATE INDEX character_name IF NOT EXISTS FOR (c:Character) ON (c.canonical_name);
CREATE INDEX rel_predicate IF NOT EXISTS FOR ()-[r:RELATED]-() ON (r.predicate);
CREATE INDEX rel_chapter IF NOT EXISTS FOR ()-[r:RELATED]-() ON (r.first_chapter);
```

**`graph.reset(book_id)`** — deletes every node and edge for one book. Required
from day one (BRANCH.md §9): Postgres is source of truth, Neo4j is a projection,
and a corrupted graph must be a re-upsert rather than a data-loss incident.

*Acceptance:* Driver survives a Neo4j container restart without an API restart.
`graph.reset()` on a book with 200 nodes and 900 edges leaves zero orphans and
does not touch another book's subgraph.

## S1.5 — Ontology config

`api/graph/ontology.py` + `api/graph/ontology.yaml` — PRD F3.1 as **data, not
code** (PRD §5.4):

```yaml
families:
  kinship:
    predicates:
      parent_of:    {inverse: child_of,   symmetric: false}
      sibling_of:   {inverse: sibling_of, symmetric: true}
      guardian_of:  {inverse: ward_of,    symmetric: false}
  romantic:
    predicates:
      married_to:   {inverse: married_to, symmetric: true}
      unrequited_love_for: {inverse: null, symmetric: false}
  # social, adversarial, structural per PRD F3.1
transitions:                # F3.3 — legal temporal supersessions
  - {from: engaged_to, to: married_to}
  - {from: friend_of,  to: enemy_of}
```

Expose: `Predicate` enum built at import, `family_of()`, `inverse_of()`,
`is_symmetric()`, `is_legal_transition(a, b)`, and a `prompt_fragment()` that
renders the predicate list for Sprint 4's extraction prompt — so the prompt and
the validator can never drift apart.

*Acceptance:* Adding a predicate to the YAML makes it valid in the API, the
enum, and the prompt with no Python change. A malformed YAML fails at import
with a clear message, not at first query.

## S1.6 — LangGraph Postgres checkpointer

Wire `AsyncPostgresSaver` against the same Postgres, run its setup migration,
and build a trivial two-node graph with an `interrupt()` between them.

*Acceptance — the one behavioural test this sprint:* start the graph, hit the
interrupt, **kill the process**, restart, resume from the checkpoint, and reach
the end node with state intact. This is PRD F5.1's acceptance criterion proven
now rather than in Sprint 7, because if the checkpointer does not work the
entire human-review design needs rethinking and it is far cheaper to learn that
in week 1.

## S1.7 — Read APIs on real empty tables

Implement against Postgres (empty, but real — no fixtures):

```
GET /api/projects/{id}/characters   → []          CharacterOut
GET /api/characters/{id}            → 404
GET /api/projects/{id}/graph        → {nodes: [], edges: []}
GET /api/graph/ontology             → the full predicate registry from S1.5
```

`/graph/ontology` is a real Sprint 1 feature, not a stub: FE1 needs it to build
edge-family colour mapping and filter controls before any edge exists.

Leave `POST /api/query` and all of `review.py` as 501 with correct response
models.

---

## Definition of Done

- [ ] Neo4j driver is a singleton, survives container restart, healthcheck exposed
- [ ] `graph.reset(book_id)` tested against a populated fixture graph
- [ ] Ontology fully data-driven; round-trip test YAML → enum → API
- [ ] **Checkpointer restart test passing** — this gates Sprint 7
- [ ] `HANDOFF.md`: ontology JSON shape for FE1, `graph.reset` signature for DO1

## Escalate immediately if

- The checkpointer restart test cannot be made to pass → **stop and escalate
  the same day.** This is a PRD-level risk, not a story-level one.
- Neo4j Community's single-database limit blocks test isolation → SCR proposing
  label-prefixed test namespacing
