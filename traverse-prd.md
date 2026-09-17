# Traverse — Product Requirements Document

**Character knowledge graphs for novels and series — ask who someone is, get the pages that prove it**

| | |
|---|---|
| **Version** | 2.1 |
| **Status** | Draft — partially built, see §8 |
| **Owner** | Priyanshu |
| **Purpose** | Freelance portfolio flagship (Toptal) + reusable client delivery base |
| **Domain** | Long-form fiction — novels, translated literary fiction, series |

**v2.1 changelog:** **series support promoted from deferred to core.** A user creates a *project* and uploads the books of a series into it; each new book appends new characters and new relations to the ones already known, rather than producing an isolated graph. This was §3.4's "deliberate seam" in v2.0 — it is now in scope, and the schema is project-scoped from the first migration. Consequences: cross-book character reconciliation (§F2.5), relationship validity measured in *series position* rather than chapter (§F3.3), two-dimensional spoiler scoping (§F4.5), and a public-domain series corpus (§7). See §3.5.

**v2.0 changelog:** domain pivot. v1.x targeted mining/construction compliance contracts. That is dropped entirely. v2 targets a single, sharper problem: **upload a novel PDF, get a character knowledge graph with page-exact evidence on every relationship.** The pivot is deliberate — see §1.4. The retrieval, eval, HITL, and ops thinking from v1.x carries over; the ontology, extraction design, and corpus are new.

---

## 1. Why this exists

### 1.1 The problem

A novel is a dense social network flattened into 400 pages of prose, and nothing in the reading experience gives you random access to it. Concretely:

- You return to book five of a series after eight months. Who is this person, how do they know the protagonist, and which of the four books you have already read established that?
- A character introduced in book one reappears in book six with a changed relationship. Nothing in your reading experience connects the two.
- You are reading *Wuthering Heights* and there are two Catherines, two Lintons, and a Heathcliff who is somehow both adopted brother and suitor. The family tree is the plot, and you cannot hold it.
- You are writing an essay, a review, a wiki, or a screen adaptation and need every page where a specific relationship is shown rather than told.
- You are translating or editing a manuscript and need to check that a character's stated relationship to another is consistent across chapters.

Today this is answered by flipping back, by a fan wiki (spoiler-riddled, only exists for popular books, often wrong), or by Ctrl-F on a name that appears 300 times.

**Why the obvious approaches fail:**

- **Keyword search** fails because characters are referred to by given name, family name, honorific form, nickname, epithet, role, and pronoun — often within one paragraph. "Kazu", "Ms. Tokita", "the waitress", "her cousin" can all be one person.
- **Vector RAG over chunks** fails because a relationship is rarely stated in one chunk. It is assembled across a hundred pages. Retrieving the top 5 similar passages for "who is Fumiko's fiancé" returns passages that *sound* like the question, not the passages that *establish* the fact.
- **Generic chat-with-PDF** fails because it hallucinates relationships that fit the genre and cannot point at a page. In fiction, a plausible-sounding invented relationship is indistinguishable from a real one to a reader who has forgotten the book — which is exactly the reader asking.

### 1.2 The insight

Relationships in fiction are **structural, evidenced, and temporal**:

- **Structural** — they form a graph, and the useful questions are graph questions ("how are these two connected", "who is in this household", "who has met whom").
- **Evidenced** — every edge was established somewhere specific on the page. An edge without a page citation is worthless; an edge with one is verifiable in two seconds.
- **Temporal** — they *change*. Strangers become lovers become estranged. An edge with no validity window is a lie about half the book. In a series that window spans *volumes*: rivals in book one, married in book seven. Validity is measured in **series position** — `(book order, chapter)` — not chapter alone.
- **Cumulative** — a series is one social network revealed in instalments. Book five does not introduce a new cast; it adds to the standing one. Treating each volume as an isolated graph throws away the thing that makes a series worth asking questions about.

A system built on those four properties answers questions a chatbot structurally cannot.

### 1.3 Success definition

**Product quality bar**

| Metric | Target |
|---|---|
| Character roster recall (named, speaking characters) | ≥ 95% |
| Character roster precision (no invented / non-character entities) | ≥ 90% |
| Alias clustering accuracy (B³ F1 over mention clusters) | ≥ 0.85 |
| Relationship precision on gold set | ≥ 90% |
| Relationship recall on gold set (major-character pairs) | ≥ 80% |
| Citation resolves to a page that actually supports the edge | ≥ 95% |
| Abstention on unanswerable / not-in-book questions | ≥ 90% |
| Full-novel ingestion (350pp) wall clock, single GPU | ≤ 25 min |
| p95 query latency | ≤ 6s, first token ≤ 1.5s |
| **Cross-book reconciliation precision** (same person correctly linked) | ≥ 95% |
| **Cross-book reconciliation recall** (returning character not duplicated) | ≥ 90% |
| **False cross-book merges** (two people collapsed into one) | ≤ 1% |

**Portfolio success**

| Metric | Target |
|---|---|
| Live demo, no signup, pre-seeded public-domain novels, works on mobile | Yes |
| Time from landing to first useful answer | < 60s |
| Published eval numbers on a labeled question set | ≥ 60 questions |
| Inbound Toptal conversations citing the project | ≥ 3 in first 60 days |
| Code reused on first paid engagement | ≥ 60% |

### 1.4 Why this domain beats the previous one (positioning note)

Contracts were a defensible market but an undifferentiated *demo*: the output is a table of fields, and every legal-AI startup shows that table. A character graph is visually and conceptually distinctive, the ground truth is publicly checkable (anyone can verify the Bennet family tree), and the corpus is free and unencumbered. The hard engineering — coreference at book scale, evidence-anchored edges, temporal validity, entity resolution under name collision — is *harder* than contract field extraction and transfers directly to any client entity-graph engagement. The buyer signal is unchanged; the demo converts better.

---

## 2. Users

### 2.1 Primary — the returning reader ("Anita")

Reads 30+ books a year, often in series, often with a long gap between volumes. Non-technical. **Needs:** "remind me who this person is and how they know the protagonist, without spoiling what I haven't read." **Will abandon** anything that spoils, or that confidently invents a relationship she then can't find on the page.

### 2.2 Secondary — the close reader ("Dev")

Student, critic, book-club lead, fan-wiki editor, or translator. **Needs:** exhaustive, citable evidence — every page where a relationship surfaces. Tolerates a review queue if it buys accuracy. (Export of evidence or graph data is confirmed out of scope — see `PRODUCT.md`.) This user is why the system must show its work.

### 2.3 Tertiary — the technical buyer ("Sanjay")

Evaluating the builder, not the book. **Needs:** the eval table, the ops dashboard, the "this ran entirely on one local GPU with zero data egress" story. In the portfolio context this is the Toptal buyer, and §7 exists for them.

---

## 3. Scope

### 3.1 In scope (v1 — ship gate)

- **Projects** — a named workspace holding one standalone novel or an ordered series
- Single-novel PDF/EPUB upload into a project, asynchronous ingestion
- Layout- and chapter-aware chunking with page provenance on every chunk
- Two-pass character extraction: roster discovery, then roster-informed relation extraction (§5.2)
- Alias / coreference resolution into canonical character records
- Typed, directed, evidence-anchored character–character relationship graph
- **Cross-book character reconciliation** — a returning character is the same node, gaining a new appearance rather than a duplicate
- **Series-position temporal validity** on edges — `(book order, chapter)`, so a relationship arc can span volumes
- Natural-language Q&A over the graph with page-exact citations and click-through to the page image
- Interactive character graph explorer
- Spoiler-safe mode scoped to a **reading position** — book *and* chapter
- Human review queue for low-confidence merges and relations
- Eval harness with published results
- Ops dashboard (cost, latency, throughput, token spend per book)
- Self-hosted inference by default, frontier API as a routed fallback
- `docker compose up` deployment

### 3.2 Out of scope (v1)

- Plot/event graphs, theme extraction, sentiment arcs
- Automatic series-order detection — the user sets book order on upload
- Merging two separate projects, or moving a book between projects
- Non-fiction, screenplays, comics, poetry
- Languages other than English (including English translations of non-English novels, which *are* in scope)
- Multi-tenancy beyond a demo workspace
- Fine-tuning — prompting, routing, and structured decoding only
- Public upload of copyrighted books (see §10)

### 3.3 Explicit non-goals

This is not "chat with any PDF." Generic capability is a positioning liability. Every screen, every prompt, every eval question is about fiction and characters. A user who uploads a tax return should get a polite "this doesn't look like a novel."

### 3.4 Deliberate seams for later

| Extension | Seam that makes it cheap |
|---|---|
| Place / object / faction nodes | Node type is an enum in the ontology config (§5.4), not branching code |
| Event graph ("how did they meet") | Relations already carry evidence spans and series-position windows; an Event node hangs off the same evidence rows |
| Non-English source text | Embedding model (BGE-M3) is already multilingual; the blocker is prompt and eval, not architecture |
| Shared universes across projects | Reconciliation (§F2.5) already matches a book's roster against a standing roster; doing it across projects is the same operation with a wider scope |

### 3.5 The series model

**A project is the unit of identity. A book is the unit of ingestion.**

| Concept | Scope | Note |
|---|---|---|
| Project | — | One standalone novel, or an ordered series. A standalone book is a one-book project; there is no separate code path. |
| Book | project | Carries `series_order`, set by the user on upload |
| Chapter, chunk, page | book | Provenance always resolves to a specific book |
| **Character** | **project** | One Harry Potter, not seven |
| **Character appearance** | character × book | Per-book first page, mention count, importance tier, and the surface forms used *in that book* |
| **Relation** | **project** | One edge, with evidence drawn from every book that establishes it |
| Evidence | relation × book | Every citation names its book |

**Ingestion is order-independent.** A user may upload book five before book one. Extraction is per-book; derived fields on the character (first appearance, series-wide tier, mention count) are **recomputed from all appearances** after each reconciliation, so a late-arriving earlier volume corrects the graph rather than corrupting it. Requiring a strict upload order would be simpler and would be wrong — users upload what they have.

**Reconciliation is a distinct stage, not a variant of alias clustering.** Within-book alias clustering (§F2.2) answers "are these two surface forms the same person in this book?". Cross-book reconciliation (§F2.5) answers "is this book's character the one the project already knows?". They share a cascade but differ in blocking evidence: within a book, co-presence in a scene proves two names are different people; across books, a character who died in volume two appearing in volume five is a flashback, a namesake, or a resurrection, and the system must not guess.

---

## 4. Functional requirements

---

### F1 — Ingestion

**F1.1 Upload**
User creates a project, then uploads a novel into it (PDF, scanned or digital; EPUB in v1.1). Max 1000 pages / 200 MB per book. For a series the user sets `series_order` on upload; for a standalone it is null. Upload returns immediately with a `book_id`; processing is asynchronous via the Celery queue.

Books may be uploaded in any order and re-ordered afterwards; re-ordering triggers recomputation of derived character fields, not re-extraction.

*Acceptance:* Upload of a 400-page PDF returns a tracking ID in under 3 seconds and never blocks the UI. Progress is reported per pipeline stage, not as an indeterminate spinner — a 20-minute job with no visible progress reads as broken.

**F1.2 Pipeline**
Ingestion is a staged, individually-retried Celery pipeline:

```
fetch → parse (Docling) → OCR fallback → chapter segmentation → chunk
      → embed → pass 1: character candidate extraction → alias clustering
      → roster confirmation [interrupt: review] → pass 2: relation extraction
      → relation aggregation & conflict resolution → graph upsert → index commit
```

*Acceptance:* Each stage is independently retryable with exponential backoff. A failure in relation extraction does not discard the parse, chunks, or embeddings — re-running resumes from the last completed stage. Failed books surface in a dead-letter view naming the stage and error, re-runnable from the UI.

**F1.3 Page provenance is mandatory**
Every chunk records `pages[]`, `page_start`, `page_end`, and the source chunk's character offsets. Nothing downstream may exist without tracing back to a page. A relation whose evidence chunks have no page provenance is rejected at upsert, not stored with a null.

*Acceptance:* Clicking any citation in any answer opens the rendered page at the right page number with the supporting sentences highlighted.

**F1.4 Chapter segmentation**
Headings are classified as chapter openers via regex fast-path with a small-LLM fallback for ambiguous forms ("One", "IV", "Prologue", "Before the Coffee Gets Cold"). Chapter number, title, and page range attach to every chunk. *(Built — see §8 Phase 1.)*

*Acceptance:* On the eval corpus, ≥ 95% of true chapter boundaries are detected and ≤ 2% of running headers / TOC entries are misclassified as chapters. Chapter boundaries are what "as of chapter N" (F4.5) and edge validity windows (F3.3) rest on, so this accuracy is load-bearing, not cosmetic.

**F1.5 Idempotency & re-ingest**
Content-hash match makes re-upload a no-op with a notice. Re-running extraction on a book preserves all `human_verified` records (F5.4).

---

### F2 — Character extraction & resolution

**F2.1 Pass 1 — candidate discovery**
A token-budgeted sweep over chunk batches extracts every character-like mention: proper names, honorific forms, epithets ("the old woman in the white dress"), and role labels ("the waitress"). Batches are assembled against the model's context budget — prompt tokens plus chunk tokens, with headroom for structured output — not a fixed chunk count.

Output per mention: surface form, chunk ID, page, chapter, and the speaking/narrating context.

*Acceptance:* On the gold corpus, ≥ 95% recall of named speaking characters. Over-generation at this stage is acceptable and expected — pass 1 optimizes recall; precision is bought back in F2.2 and F2.3.

**F2.2 Alias clustering / entity resolution**
Mentions cluster into canonical characters using, in order: exact and normalized string match; honorific and name-order stripping (`Tokita Kazu` / `Kazu Tokita` / `Ms. Tokita` / `Kazu-san` → one cluster); nickname and diminutive tables; embedding similarity over mention contexts; and an LLM adjudication pass for the residue.

**Name collision is the hard case and must be handled explicitly.** Two characters sharing a name (Catherine Earnshaw and Catherine Linton; a father and son both called Edgar) must not merge. When string evidence says "same" but contextual evidence says "different" — incompatible ages, simultaneous presence in a scene, contradictory family edges — the cluster splits and routes to human review rather than silently merging.

*Acceptance:* B³ F1 ≥ 0.85 on the labeled mention set. On *Wuthering Heights* specifically, the two Catherines resolve as distinct characters — this is a named regression test, not a general average.

**F2.3 Character record**
Each canonical character carries: canonical name, alias list with surface-form counts, first-appearance page and chapter, last-appearance page, mention count, importance tier (protagonist / major / minor / mentioned-only, derived from mention count and scene participation), and any explicitly stated attributes (occupation, age, family role) with their own evidence spans.

*Acceptance:* The character panel for any major character shows at least one page citation for every stated attribute.

**F2.5 Cross-book reconciliation (series)**
After a book's roster is resolved, reconcile it against the **project roster**: link returning characters, create genuinely new ones, and record a `character_appearance` for the book either way.

The cascade reuses §F2.2's stages, with series-specific blocking evidence:

- A character whose death is established in an earlier book, appearing in a later one → **do not auto-link.** Flashback, namesake, and resurrection are all live possibilities in fiction, and guessing wrong is a confident error in the graph.
- Contradictory kinship across books
- A generational namesake (a child named for a parent) — the same collision problem as §F2.2, across volumes

Ambiguous matches route to a `merge_across_books` review task (§F5.2). Unmatched candidates become new project characters.

After reconciliation, derived fields on the character — first appearance, last appearance, series-wide mention count and importance tier — are **recomputed from every appearance**, so out-of-order ingestion self-corrects.

*Acceptance:* Ingesting book two of a series links ≥ 95% of returning characters to their existing node and duplicates ≤ 10%. False merges ≤ 1% — a wrongly merged pair is far worse than a duplicate, because a duplicate is visible and a merge is silent. Uploading a series in reverse order produces the same graph as forward order.

**F2.4 Non-character rejection**
Places, organizations, ships, gods invoked in oaths, and book-within-book titles are classified out of the roster, not silently kept as characters. A rejected candidate is stored with its reason so the eval harness can measure precision loss and so review can overturn it.

---

### F3 — The relationship graph

**F3.1 Ontology**

*Nodes (v1):*

| Node | In v1? | Notes |
|---|---|---|
| Project | Yes | standalone or series; the identity scope for characters and relations |
| Book | Yes | title, author, translator, edition, page count, `series_order` |
| Chapter | Yes | number, title, page range |
| Character | Yes | **project-scoped** — see F2.3, F2.5 |
| Character appearance | Yes | character × book: per-book first page, tier, mention count, surface forms |
| Passage | Yes | evidence anchor — chunk, pages, quote span |
| Place | Light | only when it anchors a relation ("both work at the café") |
| Event | Deferred | §3.4 |

*Edges (character → character), grouped by family:*

| Family | Predicates |
|---|---|
| Kinship | `parent_of`, `child_of`, `sibling_of`, `grandparent_of`, `in_law_of`, `guardian_of`, `adopted_by` |
| Romantic | `married_to`, `engaged_to`, `lover_of`, `former_partner_of`, `unrequited_love_for` |
| Social | `friend_of`, `acquaintance_of`, `neighbour_of`, `colleague_of`, `employer_of`, `mentor_of`, `customer_of` |
| Adversarial | `rival_of`, `enemy_of`, `betrayed`, `deceives` |
| Structural | `co_occurs_with` (weighted, derived, not LLM-extracted) |

Direction and symmetry are declared per predicate (`sibling_of` symmetric; `parent_of` has inverse `child_of`; `unrequited_love_for` asymmetric by definition). Inverse edges are materialized on upsert so traversal never depends on the extractor having written the pair in a particular direction.

**F3.2 Every edge carries evidence — no exceptions**
An edge stores a list of evidence items, each: `chunk_id`, `page_start`, `page_end`, `chapter_no`, the supporting quote, and a per-item confidence. An edge with zero evidence items cannot be written. Edge confidence is a function of evidence count, evidence agreement, and per-item confidence — not a model self-report.

*Acceptance:* Every edge rendered anywhere in the UI is click-through to at least one page. Spot-checking 50 random edges on the gold corpus, ≥ 95% of cited pages genuinely support the claimed relation.

**F3.3 Temporal validity — in series position**
Each edge carries a validity window expressed as **series position**: `(first_book_order, first_chapter)` → `(last_book_order, last_chapter)`, plus a `status` of `active` / `ended` / `superseded`. A standalone book is series position `(1, chapter)`, so there is one code path.

When a later relation supersedes an earlier one (`engaged_to` → `married_to`, `rival_of` → `friend_of`), the earlier edge is closed and a new one opened — it is **not** overwritten. The history is the interesting part, and across a series it is the *story*.

*Acceptance:* Querying a pair whose relationship changes across volumes returns the arc ("rivals through book 1–3, friends from book 4, married in book 7") with citations at each transition, each naming its book and page. A within-book arc renders through the same mechanism.

**F3.4 Assertion provenance**
An edge records *how* it is known: `narrated` (the narration states it), `dialogue` (a character says it), or `inferred` (assembled from multiple passages). Dialogue-sourced edges record the speaker, because in fiction a character asserting a relationship is not the same as it being true — unreliable narrators and lying characters are a genre feature, not an edge case.

*Acceptance:* An answer resting on a dialogue-sourced edge attributes it ("According to Kei, ...") rather than stating it as narrative fact.

**F3.5 Aggregation & conflict resolution**
The same relation extracted from 40 chunks becomes one edge with 40 evidence items, not 40 edges. Genuine contradictions that are not temporal transitions (two different stated parents) route to `resolve_conflict` review (F5.2) rather than being resolved by confidence tiebreak.

**F3.6 Graph explorer**
Interactive force-directed view: nodes sized by importance tier, edges coloured by family, filterable by predicate family, series-position range, book, and importance. In a series project, filtering to a book shows that volume's slice of the standing graph — not a separate graph. Clicking an edge opens the evidence list with book-and-page links. Clicking a node opens the character panel.

*This screen sells the product in ten seconds — but it must be backed by the same Neo4j store the retriever queries, never a precomputed demo fixture.*

---

### F4 — Question answering

**F4.1 Query routing**
A router classifies the question and dispatches:

| Query class | Example | Path |
|---|---|---|
| Character lookup | "Who is Fumiko?" | Character record + top evidence passages |
| Relationship lookup | "How does Kazu know Kei?" | Direct edge query + evidence |
| Path / connection | "How are Heathcliff and young Cathy connected?" | Shortest-path traversal, each hop cited |
| Aggregation | "Who are all of Mr Bennet's daughters?" | Constrained graph query, exhaustive |
| Narrative / free text | "Why did they fall out?" | Graph-scoped hybrid retrieval + generation |
| Ambiguous | "What happens to her?" | Clarifying question back to the user |

*Acceptance:* Aggregation questions return complete sets from the graph, never a plausible subset assembled from retrieved prose. "All five Bennet sisters" means five.

**F4.2 Graph-constrained retrieval**
For entity-scoped questions the system resolves names to characters first, retrieves the evidence passages attached to the relevant nodes and edges, and only then falls back to hybrid vector + lexical search within that constrained set. Similarity search over the whole book is the last resort, not the first move.

*Acceptance:* On entity-scoped eval questions, graph-constrained retrieval beats naive vector-only recall@5 by a margin reported in the ablation table (§ Appendix A). If it does not, that is a finding and it gets published too.

**F4.3 Generated Cypher is templated, never free-form**
Graph queries are built from a parameterized template library keyed by query class. The LLM selects a template and fills slots; it does not emit raw Cypher. Free Cypher generation against a live database is a security and correctness liability with no offsetting benefit at this ontology's size.

**F4.4 Grounded answers**
Every factual claim carries an inline citation to book, chapter, and page, resolving to the rendered page with the span highlighted. Answers stream. Claims that cannot be grounded in an evidence span are omitted, and the system says what it could not establish.

*Acceptance:* ≥ 95% citation precision on the gold set. ≥ 90% correct abstention on questions about characters or relationships that do not exist in the book. "Not established in this novel" is a correct and expected answer.

**F4.5 Spoiler-safe mode — reading position**
The user states a **reading position**: book *and* chapter. Every query — graph, retrieval, generation — is constrained to content at or before that position. Nodes and edges whose first appearance is later are invisible, not merely unmentioned.

This matters more in a series than in a single novel, and it is the returning reader's core need (§2.1): opening book five's graph must not reveal who dies in book six.

*Acceptance:* With the position at book 2 chapter 5, no answer, graph node, edge, character, or citation references anything later. Enforced at the query layer, never by instructing the model. Leakage is its own eval metric (§F6.2), target zero.

**F4.6 Conversational follow-up**
Session context carries character and chapter scope across turns ("and her sister?" resolves against the previous answer's subject).

---

### F5 — Human-in-the-loop review

**This is the feature that separates the project from a weekend RAG demo. Build it properly.**

**F5.1 Interrupt-driven tasks**
When the pipeline hits an ambiguous merge, a contradictory relation, or a low-confidence edge on a major character, the LangGraph run **interrupts** and dispatches a task rather than guessing. State persists in the Postgres checkpointer; execution resumes on response.

*Acceptance:* Killing the worker mid-review and restarting resumes the paused run from checkpoint with no state loss.

**F5.2 Task types**

| Task type | Rendered as |
|---|---|
| `merge_characters` | "Is *Ms. Tokita* the same person as *Kazu*?" — side-by-side mention contexts with pages, merge / keep separate. Within one book. |
| `merge_across_books` | "Is book 4's *Sirius* the *Sirius Black* from book 3?" — appearance contexts from both volumes, link / keep separate. The series case (§F2.5). |
| `confirm_relation` | Proposed edge + its evidence quotes, accept / correct predicate / reject |
| `resolve_conflict` | Two contradicting relations side by side with pages — pick, or mark as a temporal transition |
| `classify_candidate` | "Is *the Nagare* a character or a place?" |
| `confirm_chapter_split` | Ambiguous heading — chapter opener or not |

**F5.3 Review queue**
Sortable by character importance, confidence, and task age. Reviewing a 400-page novel's residue must take minutes, not hours: keyboard-first (`j`/`k` navigate, `a` accept, `e` edit, `m` merge), bulk-accept for high-confidence groups, and tasks ordered so that the highest-leverage decisions (merges on major characters, which cascade through the graph) come first.

*Acceptance:* A reviewer clears 50 tasks in under 8 minutes without touching a mouse.

**F5.4 Corrections are durable and cascade**
A correction writes to the character record, the graph, and a feedback store. Corrected records are marked `human_verified` and are never overwritten by a later automated pass — a re-run that disagrees raises a fresh task instead. A confirmed merge re-points every mention and every edge from both clusters and recomputes affected edge confidences.

*Acceptance:* Re-running extraction on a reviewed book preserves 100% of human-verified records. Accepting a merge leaves zero dangling mentions or duplicate edges.

---

### F6 — Evaluation harness

**Non-optional. This is the credibility artifact.**

**F6.1 Gold dataset**
Two public-domain novels fully hand-labeled (character roster, alias clusters, major-pair relationships with page evidence), plus ≥ 60 questions spanning: character lookup, relationship lookup, path, aggregation, temporal ("were they still friends by the end?"), and deliberately unanswerable. Labeling two full novels is a real cost — budget it honestly in Phase 5 rather than discovering it late.

**F6.2 Metrics**

| Layer | Metrics |
|---|---|
| Roster | precision, recall, F1 vs. labeled roster |
| Coreference | B³ precision / recall / F1 over mention clusters |
| Relations | per-predicate precision / recall; edge-level confidence calibration (ECE) |
| Citation | page-accuracy of evidence spans (does the page support the edge) |
| Retrieval | recall@5, recall@20, MRR |
| Answers | accuracy (LLM-judge + human spot check), abstention rate |
| Spoiler safety | leakage rate at chapter N — **target 0** |
| Cost | tokens and USD per book ingested, per query |

**F6.3 Ablations**
The harness runs configuration variants and publishes the delta table:

- naive vector RAG (no graph) vs. graph-constrained retrieval
- single-pass extraction vs. two-pass roster-informed extraction
- string-only alias matching vs. full resolution cascade
- self-hosted Qwen3-8B vs. frontier API vs. routed

**This table is the single most valuable portfolio artifact.** The two-pass and graph-vs-vector rows are the ones a technical buyer will actually read.

**F6.4 Regression gate**
Evals run in CI on a reduced corpus. A PR dropping relation F1 or answer accuracy by more than 2 points fails.

---

### F7 — Ops dashboard

**F7.1 Cost telemetry** — tokens and cost per book broken out by stage (parse, embed, pass 1, pass 2, aggregation) and per query, with rolling spend. Stage breakdown matters: pass 2 dominates, and showing that you know it is the point.

**F7.2 Performance telemetry** — p50/p95/p99 by stage, time-to-first-token, pages/min throughput, GPU utilization and KV-cache pressure on the vLLM node, Celery queue depth.

**F7.3 Model routing control** — live policy editor for which stages and query classes use the local Qwen3-8B versus a frontier API, with the cost/quality trade-off shown side by side from live eval scores.

*Acceptance:* Flipping the policy changes measured cost per book within the session, and the dashboard shows both the saving and the accuracy delta. **This screen is the demo's closing argument.**

**F7.4 Pipeline health** — run history, per-stage failure rates, dead-letter depth, retry outcomes, Langfuse trace link per run.

---

## 5. Technical architecture

### 5.1 Stack

| Layer | Choice | Status | Rationale |
|---|---|---|---|
| Frontend | Vite + React + TypeScript, Chakra UI | Started | No SSR/SEO need; server/client split is pure overhead while learning React |
| Data fetching | TanStack Query + WebSocket/SSE streaming | Planned | Streaming answers, live pipeline progress |
| Graph viz | Cytoscape.js or react-force-graph | Planned | Handles 200+ nodes interactively; Cytoscape preferred for typed-edge styling |
| API | FastAPI (Python 3.11+) | Built | Same language as the AI stack, async-native |
| Task queue | Celery + RabbitMQ | Partial | Long book ingestion cannot run in a request; RabbitMQ compose service still TODO |
| Agent orchestration | LangGraph + Postgres checkpointer | Partial | Checkpointing and interrupts are what make F5.1 possible |
| Parsing | Docling (`HybridChunker`, tesserocr OCR) | Built | Layout-aware, gives page provenance per chunk for free |
| Chunking | Docling hybrid chunker, 1024-token budget, chapter-annotated | Built | §5.3 |
| Relational + vector store | Postgres 18 + pgvector | Built | One store for chunks, embeddings, evidence, review tasks |
| Graph store | Neo4j 5 Community | Scaffolded | Path queries and multi-hop traversal are the core read pattern — this is the case where Neo4j earns its place over recursive CTEs |
| Embeddings | BGE-M3 (1024-dim), self-hosted, `sentence-transformers` | Built | Multilingual, strong on long-form prose, keeps text local |
| Local inference | vLLM serving Qwen3-8B-AWQ, prefix caching, fp8 KV cache | Built | Prefix caching is a large win — pass 2 reuses a long roster prompt across every chunk |
| Frontier inference | Claude / GPT via API, routed | Planned | Hard adjudication, LLM-judge in evals. Routed, never default |
| Observability | Langfuse | Built | Per-stage traces, token accounting, prompt versioning |
| Object storage | MinIO (S3-compatible) | Planned | Page renders and source PDFs |
| Deployment | Docker Compose; GPU and CPU-only profiles | Partial | CPU profile falls back to API inference so the demo runs anywhere |

### 5.2 The two-pass extraction decision

**This is the central architectural bet and the subject of the engineering writeup.**

Single-pass extraction — ask the model for characters and relationships from each chunk independently — fails predictably on novels:

- Chunk 3 sees "Kazu" and chunk 200 sees "Ms. Tokita" with no way to know they are the same person.
- A pronoun-dense passage ("she told him she'd never forgive her sister") yields nothing without knowing who is in the scene.
- The model invents relationships to satisfy the schema when a chunk is mostly description.

The two-pass design:

**Pass 1 — discovery.** Sweep every chunk for character mentions only. High recall, no relations. Cheap, parallel, order-independent.

**Pass 2 — roster-informed extraction.** Cluster pass-1 mentions into a canonical roster, reconcile it against the project roster (§F2.5), then sweep again with that roster — canonical names, aliases, one-line descriptors — in the prompt prefix. The model now resolves pronouns against a known cast, never invents a character not on the roster, and emits relations against stable IDs.

**In a series the roster is the project's, not the book's.** That is what lets book five state a relationship about a character established in book one and attach it to the right node. It also means the roster grows with the series, so the tier-filtered roster (protagonist and major always; minor only when present in this chunk's chapter) stops being an optimisation and becomes load-bearing by volume four.

Cost is managed by vLLM prefix caching — the roster prefix is identical across every pass-2 call, so it is computed once per batch of requests rather than per chunk. This is why pass 2 is affordable, and why the ablation row comparing one-pass to two-pass carries both a quality and a cost number.

*Batching:* both passes assemble batches against a token budget (prompt + chunks + structured-output headroom against the model's 16k context), not a fixed chunk count. Chunk lengths in prose vary enough that fixed-count batching either wastes context or overflows it.

### 5.3 Chunking strategy

Docling's hybrid chunker at a 1024-token budget against the BGE-M3 tokenizer, with:

- **Chapter carry-forward** — chunks inherit the most recent detected chapter heading, so every chunk knows its chapter even mid-chapter where no heading appears.
- **Page provenance** — `pages[]` from Docling item provenance; `page_start`/`page_end` denormalized for range queries.
- **Contextualized embedding** — headings prepended before embedding (`chunker.contextualize`) so a chunk embeds with its chapter context, while the stored `text` stays clean for citation display.
- **Dialogue integrity** — an exchange split mid-turn loses its speaker. Chunk boundaries prefer paragraph breaks over hard token limits, with overlap where a split is unavoidable.

### 5.4 Ontology as config

Node types, predicates, their inverses, symmetry, and family grouping live in a config table, not in code branches — same reasoning as the v1.x schema registry. Adding `Event` or `Faction` later is a config entry plus a prompt template, not a pipeline rewrite.

### 5.5 Data model (abridged)

Postgres — chunks, evidence, extraction records, review state:

```sql
project(id, name, slug, kind)                  -- 'standalone' | 'series'

book(id, project_id, series_order, title, author, translator, content_hash,
     page_count, chapter_count, status, ingested_at)
     -- unique (project_id, series_order) where series_order is not null

chapter(id, book_id, number, title, page_start, page_end, heading_text,
        detection_method, confidence)

document_chunk(id, book_id, chapter_id, text, headings text[],
               pages int[], page_start, page_end,
               text_embedding vector(1024), tsv tsvector, token_count)

-- Characters and relations are PROJECT-scoped: one Harry Potter, not seven.
character(id, project_id, canonical_name, aliases text[], importance_tier,
          first_book_id, first_chapter, first_page, last_book_id, last_chapter,
          mention_count, attributes jsonb, human_verified bool, graph_node_id)
          -- unique (project_id, canonical_name)
          -- derived fields recomputed from appearances after each reconcile

character_appearance(id, character_id, book_id, first_page, first_chapter,
                     last_page, last_chapter, mention_count, importance_tier,
                     surface_forms text[], attributes jsonb)
                     -- unique (character_id, book_id) — the append target

character_mention(id, character_id, book_id, chunk_id, surface_form, page,
                  char_start, char_end, confidence, resolution_method)

book_character_candidate(id, book_id, surface_form, contexts jsonb,
                         cluster_key, resolved_character_id)
                         -- pass-1 output, staged before reconciliation

relation(id, project_id, subject_character_id, predicate, object_character_id,
         family, confidence, status, assertion_type, asserted_by_character_id,
         hearsay bool, human_verified bool, graph_edge_id,
         first_book_order, first_chapter, last_book_order, last_chapter)
         -- validity is SERIES POSITION: (book_order, chapter)
         -- unique (subject, predicate, object, first_book_order, first_chapter)

relation_evidence(id, relation_id, book_id, chunk_id, page_start, page_end,
                  book_order, chapter_no, quote, confidence)

review_task(id, book_id, task_type, payload jsonb, graph_thread_id,
            status, priority, created_at, resolved_at, resolution jsonb)

query_log(id, book_id, question, route, cypher_template, retrieved_ids,
          answer, citations jsonb, model_used, input_tokens, output_tokens,
          cost_usd, latency_ms jsonb, spoiler_chapter_limit, created_at)

eval_run(id, config jsonb, corpus_version, metrics jsonb, created_at)
```

Neo4j — traversal only, Postgres remains source of truth:

```cypher
(:Book)-[:HAS_CHAPTER]->(:Chapter)
(:Character {id, book_id, canonical_name, importance_tier, first_chapter})
(:Character)-[r:RELATED {predicate, family, confidence, first_chapter,
                         last_chapter, status, assertion_type,
                         evidence_ids, page_refs}]->(:Character)
```

Edges carry denormalized `page_refs` so a traversal answers "which pages" without a round trip, with full evidence hydrated from Postgres on click. Neo4j is rebuildable from Postgres at any time — a corrupted graph is a re-upsert, never data loss.

### 5.6 Query graph

```
                       ┌──────────┐
   user question ─────▶│  Router  │◀──── chapter limit (spoiler mode)
                       └────┬─────┘
       ┌──────────┬─────────┼─────────┬──────────┐
       ▼          ▼         ▼         ▼          ▼
  ┌─────────┐ ┌────────┐ ┌──────┐ ┌───────┐ ┌──────────┐
  │Character│ │Relation│ │ Path │ │Aggreg.│ │ Clarify  │
  │ lookup  │ │ lookup │ │      │ │       │ │(interrupt)│
  └────┬────┘ └───┬────┘ └──┬───┘ └───┬───┘ └────┬─────┘
       └──────────┴─────────┴─────────┘          │
                       ▼                          │
            ┌─────────────────────┐               │
            │ evidence hydration  │               │
            │  + hybrid retrieval │               │
            └──────────┬──────────┘               │
                       ▼                          │
            ┌─────────────────────┐               │
            │ grounding check     │─ fails ─▶ abstain
            └──────────┬──────────┘               │
                       ▼                          ▼
                 stream to client ◀───────────────┘
```

### 5.7 API surface (abridged)

```
POST   /api/projects                  create → project_id
GET    /api/projects                  list
GET    /api/projects/{id}             books in series order, roster size
PATCH  /api/projects/{id}/order       reorder books → recompute derived fields

POST   /api/projects/{id}/books       upload (+ series_order) → book_id
GET    /api/books/{id}/status         per-stage ingestion progress
POST   /api/books/{id}/reprocess
GET    /api/books/{id}/pages/{n}      rendered page + span highlight data

GET    /api/projects/{id}/characters  series roster, with per-book appearances
GET    /api/characters/{id}           record, aliases, attributes, evidence
GET    /api/characters/{id}/appearances   per-book presence and tier
PATCH  /api/characters/{id}           human correction
POST   /api/characters/merge

GET    /api/projects/{id}/graph       nodes + edges; filter by book, series
                                      position, family, tier
GET    /api/characters/{id}/neighbourhood
GET    /api/relations/{id}/evidence   book + pages + quotes
GET    /api/relations/arc?a=&b=       the series-spanning relationship arc
GET    /api/graph/path?from=&to=

POST   /api/query                     SSE: tokens, citations, interrupts
POST   /api/query/{thread_id}/respond

GET    /api/review/tasks
POST   /api/review/tasks/{id}/resolve → resumes graph thread

GET    /api/ops/metrics
GET    /api/ops/pipeline/runs
PUT    /api/ops/routing-policy

POST   /api/eval/run
GET    /api/eval/runs
```

---

## 6. Non-functional requirements

**Performance** — First token ≤ 1.5s p95, full answer ≤ 6s p95. Full-novel ingestion ≤ 25 min for 350 pages on one consumer GPU. Graph explorer interactive at 200 nodes / 800 edges. Review interactions ≤ 100ms perceived.

**Reliability** — Stage-level retry and resume; a failed extraction never destroys completed parse/embed work. Idempotent ingestion. Interrupted graph runs survive worker restart.

**Data residency** — The default path runs entirely locally: BGE-M3 embeddings, Qwen3-8B via vLLM, Postgres, Neo4j. Zero book content leaves the machine unless API routing is explicitly enabled, and the UI labels API-routed queries. For the portfolio this is the enterprise objection answered in advance; for copyrighted uploads it is the only defensible design.

**Observability** — Every ingestion and query fully traced in Langfuse: prompts, chunk IDs, token counts, latency by stage, cost.

**Accessibility** — Full keyboard navigation in the review queue and graph explorer. Contrast ≥ 4.5:1. The graph explorer needs a non-visual equivalent (a structured relationship list per character) — a force-directed graph alone is not accessible.

**Deployability** — `docker compose up` yields a working system with a seeded public-domain novel in under 5 minutes on a machine with no GPU (falling back to API inference). GPU profile enables the fully-local path.

---

## 7. Corpus

**Public domain — shippable in the live demo:**

| Novel | Why it earns a slot |
|---|---|
| *Pride and Prejudice* | Dense, well-documented family and courtship network; ground truth publicly checkable; the canonical aggregation test ("all five Bennet sisters") |
| *Wuthering Heights* | **The hard case.** Two Catherines, two Lintons, two Heathcliff generations, narration nested two frames deep. The name-collision and unreliable-narration regression test |
| *Frankenstein* | Nested epistolary framing — tests assertion provenance (§F3.4) since most of the book is one character's account |
| *The Great Gatsby* | First-person narrator who is himself a character; social rather than kinship network |
| *Anna Karenina* (translated) | Scale test (~350k words), Russian patronymics and diminutives — the alias-clustering stress case |

Two of these (*Pride and Prejudice*, *Wuthering Heights*) are fully hand-labeled as the standalone gold set.

**Public-domain series — the reconciliation corpus:**

The obvious series to test with is copyrighted and cannot ship in a public demo (§10). These are public domain, and two of them are *better* test cases than the obvious choice:

| Series | Books | Why it earns a slot |
|---|---|---|
| **Anne of Green Gables** (Montgomery) | 8 | **The reconciliation gold set.** Anne ages from 11 to a mother of six; Anne↔Gilbert runs enemies → rivals → friends → married across five volumes; characters marry, have children, and die between books. Every cross-book behaviour the system claims is exercised by this series, and the ground truth is unambiguous. |
| **Sherlock Holmes** (Doyle) | 4 novels + 56 stories | Recurring core cast (Holmes, Watson, Lestrade, Mycroft, Moriarty, Mrs Hudson) against an almost entirely new cast per instalment — the precision test for "don't merge two strangers who share a first name". Watson's marriages are a temporal-arc test. |
| **Oz** (Baum) | 14 | Scale test for reconciliation — a large standing roster over many volumes, with inconsistent naming between books. |
| **Barsoom** (Burroughs) | 11 | Generational: the protagonist's children become protagonists. Namesake and kinship-across-volumes stress case. |

*Anne of Green Gables* (books 1–3) is hand-labelled as the **series gold set**: roster, cross-book identity, and relationship arcs with per-book evidence.

**Local-only development corpus, never published (§10):**
- Contemporary translated fiction in `api/sample_docs/` (*Before the Coffee Gets Cold*) — Japanese honorifics, given/family name alternation, chapter structure that defeats naive regex.
- The user's own copies of a modern series (e.g. Harry Potter) — an excellent development target for reconciliation at scale and **strictly local**: it never enters the seeded corpus, the public demo, or any API-routed call.

---

## 8. Build plan

Nine one-week sprints, four agents in parallel. Full plan: [plans/](plans/), workflow: [BRANCH.md](BRANCH.md).

| Sprint | Deliverable | Status |
|---|---|---|
| **1 — Foundations & contracts** | Project-scoped v2 schema, API contracts, RabbitMQ + Celery + full compose topology, web shell, CI | Partly done (compose, parsing, embeddings exist) |
| **2 — Ingestion pipeline** | Upload into a project, staged Celery chain, chapter segmentation, page provenance, retry/dead-letter, page viewer | |
| **3 — Character extraction** | Pass-1 discovery, alias cascade, name-collision splitting, character records, roster UI | |
| **4 — Relationship graph** | Pass-2 roster-informed extraction, ontology, aggregation, evidence-anchored Neo4j upsert, graph explorer | **Ship gate** |
| **5 — Series & reconciliation** | Cross-book reconciliation, series-position validity, project roster and graph, order-independent ingestion, series UI | **The series feature** |
| **6 — Query & citations** | Router, templated Cypher, graph-constrained retrieval, grounded streaming answers, citation click-through | |
| **7 — Human review queue** | LangGraph interrupts, six task types, keyboard-first queue, durable cascading corrections | The differentiator |
| **8 — Evals & spoiler mode** | Gold sets (standalone + series), harness, ablation table, CI gate, reading-position scoping | The writeup |
| **9 — Ops & go-to-market** | Cost/latency dashboard, routing policy control, public demo, recording, writeup | The closing argument |

**Sprints 4 and 6 together are the minimum shippable portfolio piece** — a graph with cited pages that answers questions. Sprint 6 is what makes it a *series* product rather than a book product, and it sits before the query layer deliberately: building the router, Cypher templates, and retrieval filters project-aware costs almost nothing, and retrofitting project scope through them afterwards costs most of a sprint.

If time compresses: ship after Sprint 7, add 8, then 7, then 9. The eval numbers convert better than the review queue does, despite the review queue being the harder build.

---

## 9. Go-to-market artifacts

**9.1 Live demo** — public URL, no signup, pre-seeded with the public-domain corpus. Landing state offers three questions on *Pride and Prejudice* so a skimmer gets value in one click. Seeded books read-only; a rate-limited sandbox allows a small number of user uploads (§11).

**9.2 90-second recording** — a question about a half-remembered character (10s) → answer with page click-through (15s) → graph explorer, filter to kinship, spoiler slider dragged back to chapter 5 and the graph visibly shrinking (25s) → the agent pausing to ask "are these two Catherines the same person?" (25s) → ops dashboard, cost per book fully local (15s). No stack narration; show outcomes.

**9.3 Engineering writeup** — "Why two-pass extraction, with numbers." The single-pass vs. two-pass ablation, the prefix-caching cost argument, the coreference cascade, and what did not work. A second short piece on temporal edges ("relationships change; most graph extractors flatten them") is a strong follow-up.

**9.4 Repository** — public, README with architecture diagram, one-command run, eval table above the fold.

**9.5 Toptal profile** — video first. Headline names the capability (entity graphs from unstructured documents with verifiable citations), with the novel demo as proof — the buyer's document is a contract or a case file, and the demo has to read across.

---

## 10. Copyright & ethics

Non-negotiable, and a differentiator with anyone who has been burned by AI-and-books discourse:

- **The public demo serves public-domain texts only.** Verified per title, listed in the README.
- **User uploads are private, never pooled, never used for training, and deletable.** The user uploads a book they own to ask questions about it; that is the entire scope.
- **Nothing reproduces substantial text.** Citations are page references plus short supporting quotes under fair-use length, shown alongside a page number the user can open in their own copy. The system is a finding aid, not a reader.
- **Local-first inference means an uploaded book never reaches a third-party API** unless the user explicitly enables API routing, which is labeled in the UI.

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Alias over-merging collapses two distinct characters | Catastrophic and silent — the graph is confidently wrong | Contextual incompatibility checks (co-presence, age, contradicting kinship) block string-only merges; ambiguous cases route to review; *Wuthering Heights* is a named regression test |
| Hallucinated relationships | Destroys trust on first encounter | No edge without evidence spans, enforced at upsert; citation precision is a tracked eval metric; abstention is a first-class answer |
| Pass 2 cost on long novels | Ingestion too slow or expensive to demo | Prefix caching on the roster prefix, token-budgeted batching, relation extraction restricted to chunks with ≥ 2 roster mentions |
| Qwen3-8B insufficient for relation extraction | Weak headline numbers | Route hard adjudication to a frontier API and **report the split honestly** — that comparison is itself the interesting content |
| PDF page numbers ≠ printed page numbers | Citations don't match the user's physical copy | Cite PDF page and display the printed folio when detectable; state the convention in the UI |
| Neo4j adds an operational dependency | Deployment friction | Postgres remains source of truth; Neo4j is rebuildable and the compose profile handles it — but re-evaluate at Phase 3 if traversal stays shallow |
| Copyrighted upload exposure | Demo pulled, reputational damage | §10, enforced in code: public corpus is public-domain only, uploads private and local-inference by default |
| Scope creep into plot/event/theme extraction | Never ships | Phase 3 is the ship gate; events are explicitly deferred (§3.4) |
| Building this instead of paid work | Opportunity cost | Phase 3 + 4 is a shippable artifact; reassess before Phase 5 |

---

## 12. Open decisions

1. **EPUB in v1 or v1.1?** EPUB has clean structure but no page numbers — and page-exact citation is the headline promise. Default: PDF-only in v1; EPUB later with chapter-and-offset citations plus an explicit "no page numbers in this format" notice.
1a. **Reconciliation auto-link threshold.** Too loose collapses two people silently; too tight duplicates a returning character visibly. A duplicate is recoverable and visible; a false merge is neither. Default: bias tight, route the middle band to review, and set the threshold from a measured precision/recall curve in Sprint 6 rather than by intuition.
1b. **What happens when a book is removed from a project?** Characters appearing only in that book, and edges evidenced only by it, must go — but a character appearing in four other books must survive with its appearance removed and derived fields recomputed. Default: cascade by evidence, never by character. Decide in Sprint 6.
2. **Co-occurrence edges on by default?** `co_occurs_with` makes the graph look impressively dense but is not a *relationship*. Default: computed and stored, hidden behind a filter toggle, excluded from Q&A.
3. **Demo upload allowance** — far stronger demo, but abuse and cost exposure. Default: 1 book, ≤ 150 pages, rate-limited, auto-deleted after 24h.
4. **Open source scope** — public repo builds credibility, reduces reuse leverage on paid engagements. Consider open-sourcing the eval harness and ontology config alone.
5. **Importance tiering method** — mention count is crude; scene participation and dialogue volume are better but cost more. Decide at Phase 2 with measurement.

*(Resolved in v2.0: domain — novels and character graphs, replacing compliance contracts. Graph store — Neo4j, because path queries are the core read pattern.)*

---

## Appendix A — Eval ablation table (publish this)

Fill after Phase 6. Public-domain gold corpus. This table is the artifact most likely to convert a skeptical technical buyer.

| Configuration | Roster F1 | Coref B³ F1 | Relation P | Relation R | Citation acc. | Answer acc. | Cost/book | Ingest time |
|---|---|---|---|---|---|---|---|---|
| Single-pass, string-only aliases | | | | | | | | |
| Single-pass, full alias cascade | | | | | | | | |
| Two-pass, string-only aliases | | | | | | | | |
| **Two-pass, full alias cascade** | | | | | | | | |
| Above + human review pass | | | | | | | | |

| Retrieval configuration | Recall@5 | Recall@20 | MRR | Answer acc. | Citation prec. | Abstention | p95 latency |
|---|---|---|---|---|---|---|---|
| Vector only, 1024-token chunks | | | | | | | |
| Vector + BM25 hybrid | | | | | | | |
| Graph-constrained + evidence hydration | | | | | | | |
| Above, Qwen3-8B local only | | | | | | | |
| Above, frontier API only | | | | | | | |
| Above, routed (recommended) | | | | | | | |
