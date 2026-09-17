# Sprint 9 · DevOps Engineer 1

**Branch:** `ai/do1/sprint-9-ops` · **Worktree:** `../traverse-wt/do1`
**Owned:** `api/ops/**`, `docker*`, `infra/**`, `scripts/**`, `.github/workflows/**`

## Mission

Turn eight sprints of accumulated telemetry into the screen that closes the demo,
and put the thing on the internet safely.

---

**S9.1 Cost telemetry (F7.1).** Per book: tokens and USD by stage — parse, embed,
pass 1, alias, pass 2, aggregate. Per query: by route class. Rolling daily and
monthly spend. Cost per book ingested and per query answered.

Break out by stage, because PRD F7.1 is explicit that lumping them hides the
interesting content. Pass 2 dominates; showing that you know it is the point.

Cost the local model at **amortised GPU-hours**, not zero. "Local is free" is
the tell of someone who has not run inference in production, and the honest
number is more persuasive anyway.

**S9.2 Performance telemetry (F7.2).** p50/p95/p99 by stage, TTFT distribution,
ingestion pages/min, GPU utilisation and KV-cache pressure, Celery queue depth,
prefix-cache hit rate. Everything already collected since Sprint 2 — this story
is presentation, not instrumentation, which is why it is affordable now.

**S9.3 Pipeline health (F7.4).** Run history with per-stage timing, failure rates
by stage, dead-letter depth and contents, retry outcomes, and a Langfuse trace
link per run. An operator should be able to answer "what broke and where" in one
screen without opening a terminal.

**S9.4 Public deploy (§9.1).** CPU profile with API inference — no GPU on the
public host. TLS, a CDN in front of page renders, rate limiting per IP, and a
budget cap that degrades gracefully rather than running up a bill. Cost per month
documented in the README; PRD §11 lists demo hosting cost as a live risk.

**S9.5 Demo hardening (ETH-1, §12.3).** The seeded corpus is read-only and
**public-domain only, enforced in code** — a licence check at seed time that
fails the deploy, not a note in a markdown file.

Visitor uploads (PRD §12.3 default): 1 book, ≤150 pages, rate-limited,
auto-deleted after 24h, isolated per session. Scanning-abuse guard: reject
obvious non-novels early rather than burning GPU on a 150-page PDF of noise.

## DoD

- [ ] Dashboard live with real data across cost, latency, and health
- [ ] Local inference costed at amortised GPU-hours, not zero
- [ ] Public deploy TLS'd, rate-limited, budget-capped
- [ ] Licence enforcement fails the deploy on a non-public-domain seed
- [ ] Upload quota, TTL, and isolation working and tested
- [ ] Monthly running cost documented
