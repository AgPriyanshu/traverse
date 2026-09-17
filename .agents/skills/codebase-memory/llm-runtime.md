# LLM runtime

Every model call in the system. Symbols over line numbers.

## Key symbols

| Symbol | Location | Status |
| --- | --- | --- |
| `llm` (`ChatOpenAI` → vLLM), `langfuse`, `langfuse_handler` | `api/llm.py` | Prototype — mixes client, retrieval and a LangGraph definition; Langfuse is now guarded by `settings.langfuse_enabled` so import has no side effects. Split in S2.7 |
| `get_llm(purpose)` | `api/llm/client.py` | S2 |
| `structured_call(prompt, schema, *, purpose)` | `api/llm/structured.py` | S2 |
| Routing policy (purpose → model) | `api/llm/routing.py` | S2, live-switchable S9 |
| `plan_batches(...)` | `api/llm/budget.py` | S2 — **be1 depends on this by S2 Day 4** |
| `TransientLLMError` / `PermanentLLMError` | `api/llm/errors.py` | S2 |

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
`--gpu-memory-utilization 0.75`, `--max-num-seqs 16`, `--kv-cache-dtype fp8_e4m3`,
`--enable-prefix-caching`, `--enforce-eager`, hermes tool-call parser. See
`docker-compose.yml`.

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
  byte-identical across every call for a book — sort the roster deterministically.
  Target ≥80% hit rate; alerted on below that.
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
