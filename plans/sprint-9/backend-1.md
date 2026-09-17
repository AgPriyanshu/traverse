# Sprint 9 · Backend Engineer 1

**Branch:** `ai/be1/sprint-9-privacy` · **Worktree:** `../traverse-wt/be1`
**Owned:** `api/pipeline/**`, `api/extraction/**`, `api/routes/books.py`

---

**S9.8 Upload privacy (ETH-2).** PRD §10 makes a specific promise: *"User uploads
are private, never pooled, never used for training, and deletable."* Make it
true in code, because it is both an ethical commitment and the answer to the
enterprise objection.

- Uploads scoped to a session/workspace; no cross-session read path exists
- `DELETE /api/books/{id}` removes the source object, every page render, all
  chunks, characters, relations, evidence, graph nodes and edges, and the
  Langfuse traces. Cascade-verified — an orphaned page render in MinIO after a
  deletion is a broken promise.
- TTL sweeper for demo uploads (24h, per do1's S9.5)
- An audit test asserting a deleted book leaves **zero rows anywhere**, across
  Postgres, Neo4j, and MinIO. Write the test first; the deletion path is exactly
  the kind of code that looks complete and is not.

**S9.9 OCR path (§3.2) — conditional.** Docling's tesserocr is installed but
untuned, and the public-domain corpus is digital, so this has been deferred since
Sprint 2.

**Only build it if Sprint 8's retro left room.** If it is built: route to OCR
when extracted text density falls below threshold, verify page provenance
survives OCR (it is the whole product promise and OCR is where provenance
usually dies), and measure the quality delta on a deliberately scanned fixture.

**If not built, formally defer it** in `BACKLOG.md` with a reason, and say so in
the final retro. An undone story that quietly disappears is how a backlog stops
being trusted.

## DoD

- [ ] Deletion verified to leave zero rows across all three stores
- [ ] Demo upload TTL sweeper running
- [ ] No cross-session read path, proven by test
- [ ] OCR either working with measured quality, or formally deferred in writing
