# Sprint 5 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-5-series-corpus` · **Worktree:** `../traverse-wt/do1`
**Owned:** `eval/**`, `scripts/**`, `.github/workflows/**`, `api/ops/**`, `docker*`

## Mission

Get a real series into the corpus, make reconciliation quality a number, and
make ingesting eight books a single command that does not fall over halfway.

---

## S5.13 — Series corpus

**The obvious series to test with is copyrighted and cannot ship publicly**
(PRD §10). Seed these instead — and two of them are better test cases anyway:

| Series | Books | Role |
|---|---|---|
| **Anne of Green Gables** | 1–8 (label 1–3) | The reconciliation gold set. Anne ages from 11 to a mother; characters marry, have children, and die between volumes; Anne↔Gilbert runs enemies → friends → married across five books. |
| **Sherlock Holmes** | 4 novels | Precision case: a small recurring cast against a new cast per instalment. The "don't merge two strangers sharing a first name" test. |
| **Oz** | 1–6 | Scale: a large standing roster with inconsistent naming between volumes. |

Extend `seed_corpus.py` with series metadata — project name, kind, per-book
`series_order`. **Pagination stability matters more here than for standalones:**
the series gold set carries per-book page references, and a regenerated corpus
with different pagination invalidates all of them. Pin every book's checksum in
the manifest and fail the eval run loudly on mismatch.

`make seed-series` creates the projects and queues the books.

*Acceptance:* `make seed-series` on a clean machine produces three projects with
checksum-verified books in correct order. `corpus/LICENSES.md` covers every
volume.

## S5.14 — Reconciliation eval

Label cross-book identity for *Anne* 1–3: for each character, which books they
appear in and which surface forms they use in each.

```yaml
# eval/gold/anne_of_green_gables/identity.yaml
- canonical: Anne Shirley
  appears_in: [1, 2, 3]
  surface_forms:
    1: [Anne, Anne Shirley, Anne of Green Gables]
    3: [Anne, Miss Shirley]
- canonical: Davy Keith
  appears_in: [3]
```

Metrics:

| Metric | Target | Note |
|---|---|---|
| Link precision | ≥ 95% | linked pairs that are genuinely the same person |
| Link recall | ≥ 90% | returning characters not duplicated |
| **False merge rate** | **≤ 1%** | two people collapsed into one |
| Duplicate rate | ≤ 10% | same person as two nodes |
| Order independence | exact | forward vs reverse ingestion, by checksum |
| Block precision | — | blocks that were correct to block |

**Report false merges separately and never inside an F1.** A duplicate is
visible and recoverable; a merge is silent and destructive, and averaging them
into one number hides exactly the failure that matters. This asymmetry is the
finding worth writing up.

Runs nightly; PRs touching `api/reconcile/**` get the reduced version.

*Acceptance:* `make eval-reconciliation` produces the table. The
order-independence check is a hard pass/fail, not a percentage.

## S5.15 — Multi-book orchestration

`make ingest-series PROJECT=<id>` queues every book with the right ordering and
concurrency — **books within a project cannot reconcile in parallel**, because
two reconciliations racing against the same project roster will create duplicate
characters. Parse, chapter, chunk, and embed stages fan out freely; the
reconcile stage takes a per-project lock.

That lock is the story's real content. Get it wrong and you get
intermittent duplicates that only appear under load and are almost impossible to
reproduce.

Report per series: wall clock, cost per book, cost per project, how pass-2 cost
scales with roster growth, prefix-cache hit rate per book.

**The roster-growth curve is the interesting number.** If pass-2 cost per book
grows superlinearly with series length, that is a real architectural limit and it
belongs in the writeup, not buried in a retro.

*Acceptance:* Eight books ingest unattended with no duplicate characters from
races. Cost and cache trend published per book.

---

## DoD

- [ ] Three series seeded, checksummed, licensed
- [ ] *Anne* 1–3 identity ground truth labelled and schema-validated
- [ ] Reconciliation metrics nightly, **false merges reported separately**
- [ ] Order-independence a hard CI gate
- [ ] Per-project reconcile lock proven under concurrent load
- [ ] Roster-growth cost curve measured and reported
