# Sprint 1 — Schema and Change Requests

Protocol: [BRANCH.md](../../BRANCH.md) §8. Agents append; the orchestrator lands
the change on `ai-master` and announces it.

---

### SCR-1 · be1 · 2026-09-17

**Need:** `chapter` needs `human_verified boolean NOT NULL DEFAULT false`.

**Why:** `api/AGENTS.md` makes the repository layer responsible for never
overwriting a human-verified `character`, `relation` **or `chapter`**, and
`ReviewTaskType.CONFIRM_CHAPTER_SPLIT` exists in the frozen enum — so a human
can correct a chapter boundary in S7. `character` and `relation` both carry the
column; `chapter` does not, so `upsert_chapters` currently replaces every
chapter row on re-segmentation with no way to skip a corrected one. Adding it
later means back-filling after S7 has already been demoed.

**Blocking:** no. S1.3 ships with a `TODO` at the one call site; it bites in S7.

**Proposed:**
```sql
ALTER TABLE chapter ADD COLUMN human_verified boolean NOT NULL DEFAULT false;
```

---

### SCR-2 · be1 · 2026-09-17

**Need:** the last hardcoded absolute host path, `CACHE_DIR =
Path("/home/prinzz/main/my-projects/traverse/api/.cache/")` in `api/llm.py:49`,
removed — plus the `device="cuda"` next to it.

**Why:** the Sprint 1 Definition of Done is "zero hardcoded absolute paths
anywhere in `api/`", and `grep -rn "/home/" api/` is a review gate. S1.2 cleared
the ingestion path; this one is in `api/llm.py`, which is neither be1's nor
be2's owned path this sprint (it is the prototype that `api/llm/` replaces in
S2.7), so I have not touched it. The `device="cuda"` on the same
`SentenceTransformer` also defeats `EMBEDDING_DEVICE=cpu` and will OOM the
shared card if that code path is ever exercised from a worktree
([BRANCH.md](../../BRANCH.md) §9).

**Blocking:** no — nothing in the ingestion path imports it, and the chunker's
own LLM fallback imports it lazily and degrades on failure.

**Proposed:** either reassign `api/llm.py` to be2 for the sprint, or land a
two-line orchestrator fix: `settings.models_cache_dir` and
`resolve_device(settings.embedding_device)` (already exported from
`api.pipeline.chunking`).

---

### SCR-3 · be1 · 2026-09-17

**Need:** `pytest`, `pytest-asyncio` and `anyio` in the `dev` dependency group
of `api/pyproject.toml` (landed on this branch; flagging rather than asking).

**Why:** the sprint Definition of Done requires repository tests against a real
Postgres and DO1's CI runs `pytest`, but the environment had no test runner at
the freeze. be2 needs exactly the same three, so if both branches add them
independently the merge train hits a conflict in `pyproject.toml` *and*
`uv.lock` — the lock conflict being the expensive one.

**Blocking:** no, but it should be hoisted into the Sprint 2 freeze rather than
re-discovered by each agent.

**Proposed:** orchestrator owns `api/pyproject.toml` from Sprint 2 on, the same
way it owns `api/config/settings.py`; test-runner dependencies land at the
freeze.

---

### SCR-4 · be1 → do1 · 2026-09-17 · **BLOCKING (do1's S1.11/S1.12)**

**Need:** RabbitMQ configured to permit `transient_nonexcl_queues`, or pinned to
`rabbitmq:3.13-management`.

**Why:** the broker now running as `traverse-rabbitmq` is `rabbitmq:4-management`,
which resolves to **4.3.6**. In 4.x `transient_nonexcl_queues` is
`denied_by_default`, and Celery's remote-control pidbox queue is exactly a
transient non-exclusive queue. The result is not a degraded feature — the worker
cannot start at all:

```
amqp.exceptions.InternalError: Queue.declare: (541) INTERNAL_ERROR -
Feature `transient_nonexcl_queues` is deprecated.
billiard.exceptions.RestartFreqExceeded: 5 in 1s
```

and `celery -A api.workers.app inspect registered` fails with the same error.
That command is DO1's own `celery-worker` healthcheck (devops-1.md S1.12) and
the S1.1 acceptance criterion, so neither can pass until the broker is
configured. It is not fixable from the application side: Celery has no setting
for pidbox queue durability, and disabling remote control
(`worker_enable_remote_control=False`) would remove `inspect` itself.

Confirmed with `rabbitmqctl list_deprecated_features` — `transient_nonexcl_queues`
is `denied`. It cannot be flipped at runtime; it needs config plus a restart.

**Blocking:** yes, for the acceptance check. Not blocking the code: task
registration is asserted in-process against `celery_app.tasks`, which is the
same registry `inspect registered` reports
(`api/tests/workers/test_registry.py`), and all six `pipeline.*` names are
present.

**Proposed:** in the `rabbitmq` service, mount a `rabbitmq.conf` containing

```
deprecated_features.permit.transient_nonexcl_queues = true
```

or pin `image: rabbitmq:3.13-management` until Celery ships quorum-queue pidbox
support. Prefer the config line — it keeps the 4.x image and is one line.

**Resolved 2026-09-18 by do1.** Re-verified live: `celery -A api.workers.app
inspect registered` and `inspect ping` both succeed against `traverse-rabbitmq`
on vhost `/be1`, returning all six `pipeline.*` names.

One thing worth a note for be2/do1: `rabbitmqctl list_vhosts` shows the agent
vhosts as literally named `/be1`, `/be2`, `/int` (the leading slash is part of
the name, distinct from the default vhost `/`). An AMQP URL's vhost segment is
whatever follows the host:port, so reaching vhost `/be1` needs the leading
slash **percent-encoded**:

```
RABBITMQ_URL=pyamqp://guest:guest@localhost:5672/%2Fbe1
```

`.../5672/be1` (no encoding) connects to a vhost literally named `be1`, which
does not exist, and fails with `NOT_ALLOWED - vhost be1 not found`.

---

### SCR-5 · be2 · 2026-09-17
**Need:** `GraphEdgeOut.page_refs` is `list[int]`, with no book dimension.
**Why:** relations are project-scoped and evidence carries `book_id`, so in a
series a bare page number is not a citation — "page 214" of which volume?
Every other citation surface in the contracts (`EvidenceOut`, `CitationOut`)
already carries `book_id` and `series_order`; `GraphEdgeOut` is the one that
does not. The Neo4j projection therefore stores `page_refs` as
`"<book_order>:<page>"` strings and the read path would have to throw the book
away to satisfy the contract.
**Blocking:** no. Sprint 1 ships it as-is and the graph explorer is
single-book-shaped until S4.7; it bites at S5 (series arcs) at the latest.
**Proposed:** replace with a small struct, batched into the Sprint 2 freeze
rather than landed mid-sprint:

```python
class PageRefOut(BaseModel):
    book_order: int = 1
    book_id: UUID | None = None
    page: int

class GraphEdgeOut(BaseModel):
    ...
    page_refs: list[PageRefOut] = Field(default_factory=list)
```

A standalone book is `book_order=1`, so there is still one code path. FE1 would
need the regenerated client; the change is additive to every other model.

---

### DCR-1 · fe1 · 2026-09-17
**Need:** `web/src/design-system/tokens.ts` does not exist.
**Why:** `design/DESIGN.md` §3 and BRANCH.md §2 both describe it as the frozen
file FE1 imports, and `web/AGENTS.md` forbids literals in components on the
strength of it. It was never exported at the freeze. The only thing in
`web/src/design-system/` was the Vite starter's purple template theme
(`#aa3bff`, system-ui), which contradicts the settled direction in §2.
**Blocking:** no — shipped by transcribing §3 verbatim.
**Proposed:** export `tokens.ts` with the §3 palette and type/space/radius
scales. `web/src/design-system/theme.ts` already isolates the whole palette in
one `const palette` block with a comment naming this DCR, so the swap is
`import { palette } from "./tokens"` and a deletion — no component changes.
Until then `theme.ts` is the de facto token layer, which is a divergence risk
of exactly the kind BRANCH.md §8 exists to prevent.

### DCR-2 · fe1 · 2026-09-17
**Need:** light-mode `relation.social` (`#8A6A12`) measures **4.34:1** on
`sunken` (`#F2EDE4`) — below the 4.5:1 floor. It passes on `paper` (4.73) and
`surface` (4.98); dark mode passes everywhere.
**Why:** the graph legend and the relationship list sit on `sunken` wells in the
S4 artboards, and colour is a labelled channel there, not decoration.
**Blocking:** no — nothing renders relation colours until S4.
**Proposed:** darken light `social` to ≈`#7F6210` (≈4.8:1 on `sunken`), or state
in §3 that relation colours are only ever used on `paper`/`surface`. Measured
with the WCAG 2.x relative-luminance formula, all pairs, both themes.

### DCR-3 · fe1 · 2026-09-17
**Need:** §3 specifies shadow *geometry* (`0 2px 3px -1px / 0 7px 14px -10px`)
but no shadow colour or alpha.
**Why:** a shadow token cannot be built from geometry alone, and "a 1px border
plus a wide soft halo is the tell to avoid" is a statement about colour as much
as blur.
**Blocking:** no.
**Proposed:** I used the `ink` hue at low alpha
(`rgba(43, 38, 34, 0.09)` / `0.22`) so shadows read as warm rather than grey.
Confirm or replace in `tokens.ts`.

### DCR-4 · fe1 · 2026-09-17
**Need:** two measured contrast figures in §3 are optimistic.
**Why:** §3 is cited as "measured to pass 4.5:1", so the numbers get trusted.
`accent` light is **5.11:1** on `paper` (§3 says 5.4 — that is its value on
`surface`); `accent` dark is **6.16:1** on `paper` (§3 says 7.0). Both clear the
floor, so nothing is broken; the table is just off.
**Blocking:** no.
**Proposed:** restate §3's contrast column as "vs `paper`", or correct the two
figures.

---

### SCR-6 · fe1 · 2026-09-17
**Need:** a flat book list — `GET /api/books`, optionally `?project_id=`.
**Why:** the library screen (`/books`, S1.10) lists books. The frozen contract
has no book-list endpoint: books only reach the client inside
`ProjectDetailOut.books` from `GET /api/projects/{project_id}`. Rendering the
library therefore costs `1 + N` requests (`GET /api/projects`, then one detail
call per project) and the client has to flatten and re-sort them. That is an
N+1 in the first screen a user sees, and it gets worse in S5, where a project
*is* a series and a reader may have many.
**Blocking:** no — implemented as a fan-out with `useQueries`, isolated in
`useLibrary()` so it collapses to one call when this lands.
**Proposed:** `GET /api/books` → `list[BookOut]`, `project_id` and `status`
optional query filters. `BookOut` already carries `project_id`, so nothing else
changes.

### SCR-7 · fe1 · 2026-09-17
**Need:** make `type` **required** on `TokenEvent`, `CitationEvent`,
`RouteEvent`, `InterruptEvent`, `DoneEvent` and `ErrorEvent`.
**Why:** each declares `type` as a `const` **with a default**, so FastAPI emits
it as optional and `openapi-typescript` generates `type?: "token"`. The union
still narrows on a `switch`, but `undefined` is a member of every arm, so an
exhaustive `default:` cannot be proved unreachable and an event with the field
stripped type-checks. The docstring on `QueryEventEnvelope` says the envelope
exists precisely so the client carries a discriminated union; one keyword
finishes the job.
**Blocking:** no — S6 consumes these.
**Proposed:** drop the `default=` on each literal `type` field so it lands in
`required`. No wire-format change.

### SCR-8 · fe1 · 2026-09-17
**Need:** `CORSMiddleware` on the FastAPI app, dev origins only.
**Why:** `api/main.py` installs no CORS middleware, so a browser at
`:5173` cannot call `:8003` directly — the arrangement the sprint brief
describes (`VITE_API_BASE_URL=http://localhost:8003`) fails at the preflight.
**Blocking:** no — the Vite dev server proxies `/api` and `/health` to
`VITE_API_BASE_URL` instead, which is also what nginx must do in the container,
so dev and prod now share one code path and the browser is always same-origin.
**Proposed:** either add the middleware behind a settings key, or record in
`api/AGENTS.md` that the API is same-origin by design and the proxy is the
supported path. I would keep the proxy; this is a request for the decision to be
written down rather than for the middleware.

### SCR-9 · fe1 · 2026-09-17
**Need:** a documented error body on the frozen routes — at minimum an
`ErrorOut {detail: str}` schema on the `501`/`404`/`5xx` responses.
**Why:** the contract documents only `200`/`201`/`202`/`204` and `422`. Every
route returns 501 today via `HTTPException(detail=...)`, and the generated
client types that body as nothing at all, so the error surface — which S1.10
names as *the* acceptance criterion this sprint — is the one part of the client
that is hand-written and unchecked. `web/src/lib/api/errors.ts` parses `detail`
by hand, including the `422` `[{loc, msg}]` shape.
**Blocking:** no.
**Proposed:** add `responses={501: {"model": ErrorOut}, 404: {"model": ErrorOut}}`
to the frozen routes, or one app-level `responses` default.
