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
