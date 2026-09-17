# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary — the returning reader.** Someone coming back to a novel or, more often, to book five of a series after a long gap. Non-technical. Reading on a laptop or a phone, usually with the book itself to hand. Their job: *"remind me who this person is and how they know the protagonist — without spoiling what I haven't read yet."* They need the answer in seconds and they need to be able to check it on the page. They abandon a tool that spoils them once, or that states a relationship they then cannot find in the book.

**When design decisions conflict, this user wins.** Confirmed in the init interview: the evaluating buyer is persuaded by watching a real tool work well, not by a screen composed for them.

**Secondary — the close reader.** Student, critic, book-club lead, fan-wiki editor, or translator. Needs exhaustive, citable evidence: every page where a relationship surfaces. Tolerates a review queue if it buys accuracy. This user is the reason the system has to show its work rather than assert.

**Tertiary — the evaluating buyer.** Assessing the builder, not the book. Reads the eval numbers, the ops dashboard, and the fully-local-inference story. Does not get a screen designed for them.

## Product Purpose

Upload a novel as a PDF and get a character knowledge graph: every character, every relationship between them, and — for each relationship — the exact pages that establish it. Ask questions in plain English and get an answer whose every claim is a click away from the page that supports it.

For a series, the books live in one project and each new volume **adds to** the standing graph rather than producing a separate one: a returning character is the same node gaining an appearance.

Success is the returning reader getting a trustworthy, checkable answer in under ten seconds, and never being spoiled by it.

## Positioning

A novel is a dense social network flattened into 400 pages of prose, and reading gives you no random access to it. Keyword search fails because one person is a given name, a family name, an honorific, a nickname, an epithet and a pronoun — sometimes in one paragraph. Vector search over chunks fails because a relationship is assembled across a hundred pages, not stated in one. Generic chat-with-PDF fails because it invents relationships that fit the genre and cannot point at a page — and to a reader who has forgotten the book, a plausible invention is indistinguishable from the truth.

The mechanism a neighbouring product could not truthfully copy: relationships are treated as **structural** (a graph, queried as a graph), **evidenced** (no edge exists without the page spans that establish it — enforced at write time, not as a display convention), **temporal** (validity windows, so a change is an arc rather than a flattened label), and **cumulative** (a series is one social network revealed in instalments).

## Operating Context

- Books arrive as PDFs the user already owns. Ingesting a 430-page novel takes roughly twenty minutes of unattended processing, so progress must be legible rather than a spinner.
- A project holds one standalone novel or an ordered series; books may be uploaded in any order and reordered afterwards.
- The reader states a **reading position** (book and chapter). Everything — graph, answers, citations, character list — is scoped to it. Spoiler protection is a primary function, not a setting.
- Inference runs locally by default (Qwen3-8B via vLLM, BGE-M3 embeddings). Book content leaves the machine only if the user explicitly enables API routing, and the interface says so when it would.
- When the system is unsure it **stops and asks** rather than guessing: ambiguous character merges, contradicting relationships, and unclassifiable headings become human review tasks. Human corrections are permanent and are never overwritten by a later automated pass.

## Capabilities and Constraints

**Confirmed capabilities:** project and series management with book ordering; PDF ingestion with page-level provenance on every passage; chapter segmentation; character discovery with alias resolution (one person, many surface forms); cross-book character reconciliation; typed, directed, evidence-anchored relationships with series-position validity; an interactive character graph; natural-language Q&A with page-exact citations; reading-position scoping; a human review queue; published evaluation numbers.

**Constraints that shape the interface:**

- **No fact renders without its citation.** A claim the system cannot anchor to a page is not displayed, softened, or hedged — it is omitted, and the absence is stated.
- **"Not established in this novel" is a correct answer**, and must read as a considered response rather than an error.
- A relationship asserted by a character in dialogue is not the same as narrated fact; the interface must attribute it rather than state it.
- The graph must remain legible at roughly 60 characters and 900 relationships, and needs a genuine non-visual equivalent — a structured per-character relationship list — which is also the better view on a phone.
- Colour never carries meaning alone.
- Review throughput target: 50 queued decisions cleared in under 8 minutes, keyboard-only.
- English-language source text only for now; the embedding model is multilingual but prompts and evaluation are not.

**Explicitly undecided** (do not invent answers): EPUB support, given that page-exact citation is the core promise and EPUB has no page numbers; whether visitors to a public demo may upload their own books, and under what quota; whether the project is open-sourced in whole, in part, or not at all; the auto-link confidence threshold for cross-book character reconciliation.

**Confirmed out of scope:** exporting evidence, dossiers, or graph data in any form. The close reader reads and cites in place.

## Brand Commitments

The product is called **Traverse**. Lowercase "traverse" is not a styling of it.

One binding constraint on the interface, volunteered and repeated: **it must read as a well-made reading tool, not a compliance dashboard.** The graph explorer is the single place permitted to be visually loud.

## Evidence on Hand

- **Real corpus, public domain, licence-verified:** *Pride and Prejudice*, *Wuthering Heights*, *Frankenstein*, *The Great Gatsby*, *Anna Karenina*; series — *Anne of Green Gables* (8 volumes), *Sherlock Holmes*, *Oz*, *Barsoom*. Interface work should use these real characters and real quotations, never placeholder names.
- **Working code:** Docling-based parsing, chapter detection, BGE-M3 embeddings and pgvector similarity search exist and run. Everything else is planned (`plans/`, nine sprints).
- **Not yet measured, must not be presented as measured:** accuracy, recall, citation precision, reconciliation rates, latency, and cost. Every number in `traverse-prd.md` is a target. The evaluation harness that produces real ones lands in Sprint 8.
- **Does not exist:** users, testimonials, customers, pricing, a deployment, uptime, or any adoption claim.

## Product Principles

1. **Every stated fact is one click from the page that proves it.** The citation is not a footnote on the product — it is the product.
2. **Silence beats invention.** Abstention, "not established", and "we could not determine" are first-class outcomes and are designed as answers, not failures.
3. **Never spoil.** Scope is enforced at the data layer, and the interface makes the active reading position visible whenever it is filtering.
4. **Show the working.** Aliases, assertion provenance, confidence, and the reason a decision was made are visible, because that is what earns trust in an automated reading of a book someone loves.
5. **A series is one story.** Identity, relationships, and arcs span volumes; per-book views are slices of a standing whole, never separate graphs.

## Accessibility & Inclusion

Best effort, deliberately not gated on merge (confirmed in the init interview). Design intent: contrast ≥ 4.5:1 in both themes, complete keyboard operation, visible focus, colour never the sole carrier of meaning, a structured non-visual equivalent for the graph, and usable layout down to 400px. Audit findings inform work; they do not block a sprint demo.
