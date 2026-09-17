# Sprint 2 · Backend Engineer 2

**Branch:** `ai/be2/sprint-2-retrieval` · **Worktree:** `../traverse-wt/be2`

## Mission

Two things, both of which everything later depends on: the **LLM substrate**
(`api/llm/`) that be1 and you will both call for the rest of the project, and
the **retrieval layer** (hybrid vector + BM25 + rerank) that Sprint 6's answers
rest on. You are building other people's foundations this sprint — S2.8 in
particular is a hard handoff to be1 on Day 4, so treat that date as external.

## Owned paths

`api/llm/**` (new, yours permanently), `api/retrieval/**`, `api/graph/**`,
`api/query/**`, `api/routes/{characters,graph,query,review}.py`

---

## S2.7 — `api/llm/` substrate

Replace the current `api/llm.py` — which mixes a Langfuse client, a global
`ChatOpenAI`, a retrieval function, and a LangGraph definition in one module.

```
api/llm/
  client.py      get_llm(purpose) → configured chat model
  structured.py  structured_call(prompt, schema, *, purpose) with validation retry
  routing.py     purpose → model policy (local vLLM | frontier API)
  budget.py      S2.8
  errors.py      TransientLLMError vs PermanentLLMError
```

Requirements:

- **Routing by purpose, not by call site.** Purposes: `chapter_classify`,
  `character_extract`, `relation_extract`, `adjudicate`, `answer`, `judge`.
  Policy from settings, so Sprint 9's routing dashboard (F7.3) is a config
  change rather than a refactor.
- **Structured output that actually retries.** Qwen3-8B via vLLM's guided
  decoding still emits schema-invalid JSON under load. On `ValidationError`,
  retry once with the validation error appended to the prompt, then raise.
  Count both attempts in the trace — silent retries corrupt cost accounting.
- **Langfuse on every call**, tagged with `purpose`, `book_id`, `stage`.
  Sprint 9's cost breakdown (F7.1) is only possible if these tags exist from now.
- **Concurrency limit.** A shared `asyncio.Semaphore` sized from settings —
  `--max-num-seqs 16` on vLLM means an unbounded fan-out from a Celery worker
  just queues and times out.
- `errors.py` classification decides what Celery retries. Getting this wrong
  means be1's pipeline retries a malformed prompt four times.

*Acceptance:* A forced schema violation retries once and succeeds. Killing vLLM
mid-call raises `TransientLLMError` and Celery retries; a 400 raises
`PermanentLLMError` and does not.

## S2.8 — Token-budget batcher · **hard handoff to be1, Day 4**

PRD §5.2 and the project TODO: batches are assembled against a token budget —
prompt + chunks + structured-output headroom against the model's 16k context —
not a fixed chunk count.

```python
def plan_batches(
    items: Sequence[T],
    *,
    prompt_tokens: int,
    text_of: Callable[[T], str],
    max_context: int,
    output_reserve: int,
    safety_margin: float = 0.9,
) -> list[BatchPlan[T]]
```

Count with the **model's own tokenizer**, not a characters/4 estimate — prose
with dialogue and em-dashes tokenizes differently from the estimate and the
error compounds across 40 chunks into a context overflow.

A single item exceeding the budget is split, never silently dropped, and the
split is reported in the plan so callers can stitch results.

*Acceptance:* Property test over randomly-sized inputs — no plan exceeds the
budget, no item is lost or duplicated, and a single oversized item is split.
Ship to `ai-master` by **Day 4** or be1's Sprint 3 starts blocked.

## S2.9 — Hybrid retrieval

`api/retrieval/hybrid.py` — PRD F4.1 minus the graph:

- Dense: pgvector cosine over `document_chunk.text_embedding`, top 50
- Lexical: `ts_rank_cd` over the `tsv` generated column, top 50
- Fuse with **reciprocal rank fusion**, k=60. RRF over score normalisation
  because the two scores are not commensurable and normalising them is where
  hybrid search usually goes wrong.
- Filters: `book_id` (always), `chapter_lte` (the Sprint 8 spoiler hook — add
  the parameter now, it costs nothing and retrofitting a filter through a
  retrieval stack is miserable), `character_ids`

`GET /api/search?book_id=&q=&limit=&chapter_lte=` returning chunks with page
ranges and both component scores — fe1 needs the scores for the chunk inspector,
and *you* need them to debug ranking.

*Acceptance:* Both arms independently return sane results on the seeded corpus;
RRF beats either alone on a 15-question smoke set committed to the repo. If it
does not, that is a finding — record it in the retro rather than burying it.

## S2.10 — Reranker, behind a flag

BGE-reranker cross-encoder over the top 50, `RERANKER_ENABLED` default off.

PRD §5.1 calls the reranker "the largest single quality lever per unit cost" —
**verify that claim rather than inheriting it.** Measure recall@5 and added
latency on the smoke set with it on and off. It is a row in the Sprint 8
ablation table (F6.3) and the number should be real by then.

*Acceptance:* Both configurations measured, numbers in `RETRO.md`. Reranker
adds ≤400ms p95 for 50 candidates or it is off by default and the retro says why.

---

## DoD

- [ ] `api/llm/` is the only place a model is called from, anywhere in the codebase
- [ ] Batcher merged by **Day 4** with be1 notified in `HANDOFF.md`
- [ ] Hybrid vs. single-arm retrieval measured, not asserted
- [ ] Every LLM call traced in Langfuse with `purpose` and `book_id`
- [ ] `HANDOFF.md`: `plan_batches` signature, `structured_call` signature,
      purpose enum, `SearchResult` shape for fe1
