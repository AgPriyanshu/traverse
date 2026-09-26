# LLM runtime

Every model call in the system. Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| `get_llm(purpose)`, `semaphore()` | `api/llm/client.py` | **Built** |
| `structured_call(prompt, schema, *, purpose, book_id, stage)` | `api/llm/structured.py` | **Built** |
| Routing policy (`route_for`, `ModelRoute`) | `api/llm/routing.py` | **Built**, live-switchable S9 |
| `plan_batches(...)` | `api/llm/budget.py` | **Built** — be1 depends on this from S3 |
| `TransientLLMError` / `PermanentLLMError` / `classify_call_error` | `api/llm/errors.py` | **Built** |
| `trace_generation(...)` | `api/llm/tracing.py` | **Built** |

`api/llm.py` (the Sprint 1 prototype — global `ChatOpenAI`, a Langfuse
handler, a raw-cosine retrieval function and a LangGraph definition in one
module) is **gone**, deleted at S2.7. `api/pipeline/chunking.py`'s
`_classify_chapter_heading` still imports it as of this commit — be1's own
S2.3 migrates that call to `structured_call`; see `plans/sprint-2/HANDOFF.md`.

**`api/llm` is the only place a model may be instantiated.** A call path that
bypasses it is invisible to the cost dashboard and the routing policy.

## Purposes

Routing is by **purpose, not call site**, so S9's routing dashboard is a config
change rather than a refactor:

```
chapter_classify · character_extract · relation_extract
adjudicate · answer · judge
```

`judge` must route to a **frontier** model — an 8B grading its own output is not
a measurement.

## Serving

vLLM, `Qwen/Qwen3-8B-AWQ`, `awq_marlin`, port 8080, `--max-model-len 16384`,
`--gpu-memory-utilization 0.85` (S4.15, was `0.75` — see the KV-cache gotcha
below), `--max-num-seqs 16`, `--kv-cache-dtype fp8_e4m3`,
`--enable-prefix-caching`, `--enforce-eager`, hermes tool-call parser. See
`docker-compose.yml`. **Real fan-out is 8, not 16**: `settings.llm_max_concurrency`
(`api/config/settings.py`, frozen) gates every call through a shared semaphore
below vLLM's own `--max-num-seqs 16` and `api/relations/extract.py`'s
`_PARALLEL_CHUNKS = 16` — both of those app-level 16s are aspirational
headroom, not the real concurrency ceiling.

## Gotchas

- **Bound concurrency.** A shared `asyncio.Semaphore` sized from settings.
  `--max-num-seqs 16` means an unbounded fan-out from a Celery worker just queues
  and times out.
- **Structured output must retry.** Qwen3-8B under load emits schema-invalid
  JSON even with guided decoding. Retry once with the `ValidationError` appended,
  then raise. **Count both attempts in the trace** — silent retries corrupt cost
  accounting.
- **Error classification drives Celery retry.** Getting it wrong means the
  pipeline retries a malformed prompt four times. Transient = network, 5xx,
  timeout. Permanent = 400, schema violation after retry, malformed input.
- **Prefix caching is the cost argument.** Pass 2's stable prefix must be
  byte-identical across every call for a book — sort the roster deterministically
  (`Roster.prompt_block`, `ontology.prompt_fragment` both are; confirmed by
  reading, S4.15). Target ≥80% hit rate; alerted on below that.
- **80% is a structural ceiling problem for Pride and Prejudice, not (mainly) a
  bug** (S4.15, root-caused against a real run: `plans/sprint-4/HANDOFF.md`).
  vLLM's hit rate is `hit_tokens / total_prompt_tokens`; only the fixed prefix
  is ever a hit, so the ceiling — even with a perfectly warm, never-evicted
  cache — is `prefix_tokens / (prefix_tokens + avg_chunk_tokens)`. Measured on
  the live book: a 73-character roster prefix is 1,434 tokens; the prefilter's
  candidate chunks average 631 tokens; ceiling ≈ 1434/(1434+631) ≈ **69.4%**,
  which is where the observed 65–76% actually sits. Raising
  `--gpu-memory-utilization` (0.75 → 0.85, +39% KV-cache budget, 3.05 → 4.25
  GiB on the 12GB card) recovers a few points of eviction-driven loss on top
  of that ceiling but cannot cross it — the real lever is the roster-prefix
  to chunk-size ratio (a bigger roster, or smaller/scene-batched chunks, not
  concurrency or memory).
- **The reported number was also silently the wrong window.** `hit_rate_between`/
  `fetch_vllm_cache_counters` (`api/ops/vllm_metrics.py`) exist to delta two
  counter snapshots around one run, but nothing called them — every consumer
  (`relation_cost.py`, `extraction_cost.py`, `pipeline_status.py`) read
  `fetch_vllm_cache_stats`, vLLM's lifetime-cumulative average since the
  server's last boot, silently blending in pass-1 calls, the relation
  verifier's `adjudicate` calls, and (vLLM being a host singleton shared by
  every agent's worktree, BRANCH.md §9) any other agent's concurrent traffic.
  Fixed by wiring the delta helpers into `scripts/ingest_book.py` and
  `scripts/nightly_corpus_ingestion.py`, which can snapshot immediately before
  and after the run they themselves drive; the ops endpoints still report the
  lifetime average (now documented as such) since they have no "before"
  snapshot to delta against after the fact.
- **Token counting uses the model's own tokenizer.** A characters/4 estimate
  compounds across 40 chunks into a context overflow. `plan_batches` splits an
  oversized item rather than dropping it, and reports the split.
- **Every call is traced in Langfuse** with `purpose` and `book_id`. The cost
  breakdown (F7.1) reads those tags; a call without them is invisible spend.
- **Private uploads must never reach a third-party API** unless the user
  explicitly enabled routing. Enforced at the client layer, below the policy —
  a policy edit must not be able to bypass it (NFR-residency, ETH-4).
- Local inference is costed at **amortised GPU-hours**, not zero. "Local is
  free" is wrong and the honest number is more persuasive.

## Shared GPU

One GPU, one vLLM on `:8080`, shared by both backend agents
([BRANCH.md](../../../BRANCH.md) §9). Continuous batching means concurrent load
degrades latency, not correctness — but **any timing measured from a worktree is
invalid**. Performance numbers come from the integration host only.

## Related

[character-graph.md](character-graph.md) · [query-path.md](query-path.md) ·
[infra-topology.md](infra-topology.md) · [plans/sprint-2/backend-2.md](../../../plans/sprint-2/backend-2.md)
