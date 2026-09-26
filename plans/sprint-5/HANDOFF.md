# Sprint 5 — Handoffs

## be1 → be2, Day 2: the project-roster query shape for S5.5

`pipeline.reconcile_characters` (S5.1-S5.4, `api/reconcile/`) is merged. What
it changed that S5.5's project-scoped pass 2 needs to know about:

**The roster query.** `Character` was already `project_id`-scoped
(`uq_character_project_name`), so the query you want is the same shape
`api/reconcile/repository.py::list_roster_characters` already uses:

```python
select(Character).where(Character.project_id == project_id)
```

No book filter — that's the whole point of S5.5 ("the roster is the
project's, not the book's"). For tier-filtering (protagonist + major always;
minor only when present in *this* book or chapter), join `CharacterAppearance`
on `(character_id, book_id)` — that row's `importance_tier` is the *per-book*
tier (it can legitimately differ from `Character.importance_tier`, which is
now the series-wide max across every appearance, recomputed after every
reconcile — see below). "Present in this chapter" needs `CharacterMention`,
not `CharacterAppearance` (appearance is book-granularity only).

**`Character.canonical_name` can now change after a book you already
processed.** Reconciliation may rename a character's canonical form (e.g. a
book-1 "Anne Shirley" absorbing book-3's "Miss Shirley" settles on whichever
of the character's full alias set is most complete — usually "Anne Shirley",
but not guaranteed) and always recomputes `Character.aliases` as the full
project-wide union, never just the most recent book's. If your pass-2 prompt
caches anything keyed on a character's name string across books, key it on
`Character.id` instead, or re-read the roster fresh per book.

**Ordering for prefix caching.** `reconcile_characters` runs before
`relations.extract` in the frozen chain (`api/tasks.py::STAGES`), so by the
time pass 2 reads the roster for a given book, that book's own reconciliation
has already happened — the roster it sees already reflects any merge this
book's own characters just went through. Sort deterministically as
`character-graph.md` already says; nothing about reconciliation changes that
requirement, it just means the *set* being sorted may include a
newly-recomputed canonical name it wouldn't have on a book processed before
S5.1 landed.

**New column, not a new migration.** `BookCharacterCandidate.resolved_character_id`
(already in the Sprint 1 freeze's model, migration `0006`) is now actually
written, by `resolve_aliases` and repointed by any later merge. Nothing for
you to migrate; mentioned in case you grep for it and want to know who owns
writing it (`api/extraction/repository.py::set_resolved_character_ids`,
`api/reconcile/repository.py::merge_character`).

**Locking.** `reconcile_characters` takes `api/workers/locks.py::
project_roster_lock(project_id)`, a distinct advisory-lock key from
`book_roster_lock`. If S5.5's pass-2 stage ever needs to read-then-write the
roster (it currently only reads), take the same lock rather than inventing a
third one.
