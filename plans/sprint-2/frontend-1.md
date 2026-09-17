# Sprint 2 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-2-ingestion` · **Worktree:** `../traverse-wt/fe1`

## Mission

Make ingestion legible and build the page viewer. The viewer is the most
important component in the product — every citation from Sprint 6 onward lands
in it, and the whole value proposition ("fetch the exact pages") is only as good
as this component. Build it properly now, when it has no deadline pressure on it.

## Design input — read before writing any component

Open [design/DESIGN.md](../../design/DESIGN.md) and the Claude Design canvas URL
recorded there. Implement the artboards listed for **this sprint** in the
artboard map (§1). Use the frozen tokens from
`web/src/design-system/tokens.ts` — never a literal colour, spacing value, or
font size. Where the canvas and `DESIGN.md` disagree, DESIGN.md wins; where
something you need is missing from both, file a **DCR** (BRANCH.md §8) rather
than inventing a token in your worktree.

---

## Owned paths

`web/src/**`, `web/package.json`, `web/tests/**`

---

## S2.11 — Upload flow

Wire `POST /api/books` for real. Drag-and-drop with click fallback, PDF only,
200 MB cap. Real upload progress from `XMLHttpRequest.upload.onprogress` —
`fetch` gives you no upload progress and a 200 MB file over a slow link with a
spinner reads as frozen.

Handle: already-ingested (`200` not `202`) → route to the existing book with a
toast, not an error; oversize; wrong type; network failure mid-upload with a
retry that does not re-hash client-side.

*Acceptance:* Real progress percentage. Every documented error path renders a
specific message — never "Something went wrong".

## S2.12 — Live ingestion progress

`/books/:id` — the vertical stepper from S1.10 fed by
`GET /books/{id}/status`, polling at 2s while non-terminal, stopping on terminal.

Per stage: name in human language ("Reading the PDF", not
`pipeline.parse_and_chunk`), state, duration, attempt count when >1. Failed
stage shows the error text and a **Retry from this stage** button hitting
`POST /reprocess?from_stage=`.

An overall estimate matters more than it looks — a 20-minute job needs a
credible "about 12 minutes remaining", derived from completed stage durations
against the book's page count. PRD F1.1: invisible progress reads as broken.

Poll with `refetchInterval`, and back off to 10s after 5 minutes so a
long-running tab does not hammer the API.

*Acceptance:* A full ingestion is watchable start to finish without a manual
refresh. Failure state is unambiguous and actionable.

## S2.13 — Chapters and chunks

**`/books/:id/chapters`** — list with number, title, page range, chunk count.
Detection method shown as a subtle badge (`regex` / `llm`) — this is a debugging
affordance for the team and a trust signal for the user, and it costs one chip.

**Chunk inspector** — a drawer, not a page. Chunk text, chapter, page range,
token count, and (from `GET /api/search`) the dense and lexical scores when it
arrived via search. Clicking the page range opens the viewer at that page.

## S2.14 — Page viewer

The component everything later depends on. `pdfjs-dist`, rendering from the
signed URL in `PageRenderOut`.

- Page navigation: next/prev, jump-to-page, keyboard `←`/`→`
- Zoom: fit-width, fit-page, 100%, 200%
- **A highlight API, built now, used in Sprint 6:**
  `<PageViewer bookId page={n} highlights={[{page, x, y, w, h, kind}]} />`
- Highlights render in the PDF coordinate space be1 documents in `HANDOFF.md` —
  **agree this with be1 on Day 2**, do not infer it from a sample
- Deep-linkable: `/books/:id/pages/42?highlight=…` must survive a reload, because
  Sprint 6's citations are links
- Lazy-load neighbours ±1; never fetch a whole book of PNGs

*Acceptance:* Jump to page 300 of a 430-page book in under a second on a warm
cache. A highlight rectangle lands on the right words at 100% and 200% zoom.
Mobile: page fits width, controls reachable one-handed.

---

## DoD

- [ ] Ingestion watchable end to end with no refresh
- [ ] Page viewer deep-links, highlights, and is keyboard-navigable
- [ ] Coordinate contract with be1 written down in `HANDOFF.md`, not assumed
- [ ] `tsc --noEmit`, `oxlint`, and 400px-width pass clean
