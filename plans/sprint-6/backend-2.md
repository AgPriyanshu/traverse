# Sprint 6 · Backend Engineer 2

**Branch:** `ai/be2/sprint-6-query` · **Worktree:** `../traverse-wt/be2`
**Owned:** `api/query/**`, `api/retrieval/**`, `api/graph/**`, `api/llm/**`,
`api/routes/query.py`

## Mission

Turn the graph into answers. The graph is only as valuable as the questions it
can be asked in plain English, and the thing that separates this from a chatbot
is that **every claim is traceable and unsupported claims are dropped rather
than smoothed over**.

---

**S6.1 Router (F4.1).** Classify into the PRD's six classes. Use structured
output with the class *and* the extracted entities in one call — a second
entity-extraction pass doubles latency on the critical path. Build a 60-question
labelled routing set and publish the confusion matrix; a misrouted aggregation
question becomes a hallucinated list, so the aggregation row matters most.

**S6.2 Templated Cypher (F4.3).** A parameterised template per class in
`api/query/templates/`. The LLM picks a template ID and fills named slots; it
never emits Cypher. Validate slots against the ontology before execution. Assert
in tests that no code path can send a model-authored string to Neo4j.

**S6.3 Graph-constrained retrieval (F4.2).** Order matters: resolve names to
character IDs (be1's S6.7) → pull node and edge evidence chunks → *then* hybrid
search within that constrained set → whole-project vector search only as last
resort. Scope defaults to the **project**; a single book is a filter, never a
different endpoint. Log which tier answered; Sprint 8's ablation needs the breakdown, and it
is the writeup's central claim.

**S6.4 Grounding and abstention (F4.4).** After generation, verify each claim
against retrieved evidence. Unsupported claims are **removed**, and the answer
states what could not be established. "Not established in this novel" is a
correct answer, and the abstention rate is a headline metric — do not let the
model hedge its way to a technically-non-false answer instead.

Hearsay handling: an answer resting on a `hearsay` edge must attribute it
("According to Mrs Bennet…"). This is F3.4 paying off.

**S6.5 Streaming (F4.4).** SSE with discriminated events: `token`, `citation`,
`route`, `interrupt`, `done`, `error`. Citations stream as their own events so
fe1 renders chips inline as the sentence arrives. Verify `proxy_buffering off`
survived from Sprint 1 — this is where it would silently break.

**S6.6 Conversation memory (F4.6).** Persist turns; carry character and chapter
scope. Resolve "her sister" against the previous turn's subject. Cap context by
tokens, not turn count, and summarise beyond the cap.

## DoD

- [ ] Router matrix published; aggregation recall 100% on gold rosters
- [ ] No free-form Cypher reachable, proven by test
- [ ] Retrieval tier logged per query
- [ ] Abstention works on genuinely unanswerable questions
- [ ] `HANDOFF.md`: SSE event schema for fe1 — **Day 2**
