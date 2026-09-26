# Sprint 5 — Standup

## be2 — 2026-09-26

**Landed:** S5.5 (project-scoped, tier-filtered pass-2 roster), S5.6 (series
-position validity — confirmed the (book_order, chapter) mechanism was already
built in Sprint 4; fixed a real gap, a missing `enemy_of -> rival_of` ontology
transition, that would have made the demo's Anne/Gilbert arc report as a
conflict), S5.7 (cross-book aggregation — confirmed already project-wide from
S4, added regression coverage), S5.8 (`/characters/{id}/appearances`
implemented; book-removal cascade — the relations/graph half —
`api/graph/cascade.py`). Also fixed the carried Neo4j `AsyncDriver`
stale-event-loop bug (same class as Sprint 4's semaphore fix), with a
regression test.

**Not verified yet:** full `docker compose --profile test` run (in progress at
time of writing — see this branch's final commit); prefix-cache hit rate and
off-roster rate at series length, which need a real multi-book corpus (do1's
S5.13/S5.14).

**Blocked on nothing**, but flagging for be1: `DELETE /books/{id}`
(`api/routes/books.py`) is still `not_implemented("be1", "S8.8")` — the
book-removal cascade's character-side half (mention/appearance deletion,
orphan sweep, derived-field recompute from remaining appearances) looks like
it belongs to S5.3 but I don't see it landed in this checkout yet. My half
(`api/graph/cascade.py::remove_book`) is ready and tested; integration
contract is in `HANDOFF.md`. The two halves are order-independent (FK cascade
on `character.id` handles the interaction), so no sequencing coordination
needed beyond both existing before `delete_book` is wired up.

---
