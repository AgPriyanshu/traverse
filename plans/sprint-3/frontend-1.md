# Sprint 3 · Frontend Engineer 1

**Branch:** `ai/fe1/sprint-3-characters` · **Worktree:** `../traverse-wt/fe1`

## Mission

Make the roster feel like a reference you would actually use while reading. This
is the first screen that delivers the product's promise, and the test is
specific: someone returning to a novel after eight months should be able to
answer "who is this again?" in under ten seconds without being spoiled.

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

`web/src/**`, `web/tests/**`

---

## S3.10 — Character list

`/books/:id/characters`. Grouped by importance tier with protagonists first —
a flat alphabetical list of 60 names is a phone book, not an answer.

Per character: canonical name, top 3 aliases as chips (+N more), mention count,
first appearance as a `<PageRef>`, a sparkline of mentions across chapters.

The sparkline earns its space — it shows at a glance whether someone is present
throughout or confined to a stretch, which is exactly the question a returning
reader has. Data comes from be2's per-chapter histogram; do not compute it from
paginated mentions.

Controls: search (alias-aware — typing "Lizzy" finds Elizabeth Bennet), tier
filter, sort by mentions / first appearance / name.

*Acceptance:* 60-character roster renders in <100ms after data arrives. Alias
search works. Usable at 400px — cards stack, chips wrap, nothing truncates to
ambiguity.

## S3.11 — Character detail

`/books/:id/characters/:characterId`.

- **Header** — canonical name, tier, mention count, chapter span
- **Aliases** — every surface form with its count, so the user sees *why* the
  system thinks these are one person. This is the transparency that earns trust
  in a merge, and it is cheap to show.
- **Attributes** — each with its `<PageRef>` citation. No citation, not rendered.
- **Mentions timeline** — chapters on x, mention count on y, click a bar to
  filter the mention list. Load `dataviz` guidance before building this chart.
- **Mention list** — surface form, page, a context snippet, click → page viewer
  with the mention highlighted
- **Relationships panel** — an empty placeholder this sprint, filled in Sprint 4.
  Put it in the layout now so Sprint 4 is a data change, not a redesign.

*Acceptance:* Every displayed fact traces to a page in one click. Timeline and
list stay in sync. Keyboard navigable.

## S3.12 — Alias and mention inspector

A drawer over the detail page for auditing a merge: every mention grouped by
surface form, with context, page, and the `resolution_method` that put it in the
cluster (`exact` / `honorific` / `nickname` / `embedding` / `llm`).

Showing the resolution method is a deliberate trust affordance. "Why does the
system think Lizzy is Elizabeth?" → "nickname table" is a satisfying answer;
silence is not. It also makes Sprint 7's review UI a small extension rather than
a new screen.

*Acceptance:* A reviewer can audit a 200-mention cluster without leaving the
drawer, and reach any mention's page in one click.

---

## DoD

- [ ] Roster answers "who is this?" in <10s, verified by walking a real novel
- [ ] Every fact on screen is click-through to a page
- [ ] Alias-aware search
- [ ] Relationships placeholder in the layout, ready for Sprint 4
- [ ] 400px and dark mode clean; contrast ≥ 4.5:1 on chips and sparklines
