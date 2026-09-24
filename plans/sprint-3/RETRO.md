# Sprint 3 Retrospective

**Dates:** 2026-09-22 → 2026-09-23
**Goal:** upload *Pride and Prejudice*, get an accurate character roster, with the two Catherines in *Wuthering Heights* kept apart.
**Outcome:** Partially met. All stories are built and merged, and `extract_characters` completes on the full real book. The quality targets are not met: the roster is not yet accurate (see section 2).

## 1. Delivered

| Story | Owner | Status | Notes |
|---|---|---|---|
| S3.1–S3.5 | be1 | Built, merged | Pass-1 discovery, rejection, alias cascade, collision guard, tiering. |
| S3.6–S3.8 | be2 | Built, merged | Read APIs, merge/split, similarity service (threshold 0.65 from a measured curve). |
| S3.9 | be2 | Done | Written findings in HANDOFF.md. |
| S3.10–S3.12 | fe1 | Built, merged | Roster, detail, inspector. Sparkline is a placeholder pending SCR-8 (now landed). |
| S3.13–S3.15 | do1 | Built, merged | Gold rosters, quality metrics, cost reporting. |
| A-2.5 | do1 | Fixed | 16pt bold headings; 49/51 chapters detected on real P&P. |

## 2. Not yet verified (deferred to the final test pass)

- `extract_characters` completing on the full real book after the length-limit halving fix.
- Roster recall/precision, B³ F1 and the two-Catherines result on real output.
- Tiering decision (PRD §12.5): both methods are implemented, but no measurement has been run.
- One test, `TestSplitRetryOnLengthLimit::test_recursively_halves_a_batch_whose_real_reply_overflows_the_reserve`, failed in a run that used a stale image, so it is unconfirmed either way.

## 2b. Real-book result (2026-09-24, full Pride and Prejudice, live vLLM)

- `extract_characters` completes in about 27 minutes. It was blocked by one root cause: Qwen3-8B's reasoning mode. A one-sentence probe used 1,800 completion tokens with thinking on and 30 with it off. The fixes were `llm_enable_thinking=false`, a `max_tokens` cap, `LengthFinishReasonError` mapped to `LengthLimitError`, and concurrent batches.
- `resolve_aliases` crashed after 30 minutes with a `StaleDataError` on `bookcharactercandidate`, possibly a race between duplicate runs. It is also far too slow.
- The roster has 153 characters against a gold set of 25. Pronouns ("she", "he") rank as major characters, some canonical names are descriptors ("my brother Gardiner"), and Elizabeth does not collect her aliases. Precision, recall and B³ are therefore unmet. No `sprint-3` tag until they are measured and fixed.

## 2c. Measured on the real corpus (live stack, do1's completed gold rosters)

| | Pride and Prejudice | Wuthering Heights | Target |
|---|---|---|---|
| Roster precision, protagonist to minor tiers | 0.929 | 0.609 | 0.90 |
| Roster recall, protagonist to minor tiers | 0.963 | 0.933 | 0.95 |
| B³ F1 (alias clustering) | 0.872 | 0.804 | 0.85 |
| Tier accuracy | 0.778 | 0.600 | not set |

- **P&P:** meets the targets after be1's roster fixes. Merges (Mr. Bingley into Caroline, Darcy into Miss Darcy) were fixed by veto rules and pinned by a regression test built from real candidates.
- **Wuthering Heights (headline):** Catherine Earnshaw and Catherine Linton are two rows, but the split is wrong. The elder row holds 2 mentions, the "Cathy" and "Catherine" mentions of the elder Catherine are folded into "Catherine Linton" (184), and the younger Cathy is a separate "Miss Cathy" row. Nelly, Ellen Dean and Mrs. Dean are three rows for one person, and the Linton family is fragmented. **The headline result is not met, so `sprint-3` is not tagged.**
- A failure on this book also showed that a single runaway attribute-extraction call could fail the whole stage and lose the roster. Attribute extraction now fails soft.

## 3. What went wrong

- Three bugs only appeared on the real 245-page book, not in unit tests or the 20-page fixture:
  1. A heading with no body text desynced the chapter carry-forward cursor.
  2. A flat output reserve did not match greedy batch packing.
  3. A dense batch overflowed the completion; the fix is recursive halving.
- A cross-agent adapter (be1 to be2 similarity) passed its own tests only because its ImportError fallback hid a signature mismatch.
- The `test` image tag is shared across worktrees, so a run without a fresh build tests the wrong tree. Hit by three agents and the orchestrator.
- Docker Desktop's WSL integration dropped mid-sprint, and credential-store errors broke image builds.

## 4. Action items

- A-3.1: Run the real seeded corpus through the stage under test before calling a story done.
- A-3.2: Give the `test` image a per-worktree tag.
- A-3.3: Cross-agent adapters need one test against the real signature, not only the fallback path.
- A-3.4: Sprint 4 pass 2 should catch `LengthLimitError` and split, as discovery does.
- A-3.6: Batch-size, reserve and halving work treated symptoms; find the root cause from one probe of the real model before tuning constants.
- A-3.5: Remaining SCRs: boto3 in pyproject/uv.lock, `MentionOut.span`, chunks `chapter_id` filter, `MetricsOut` cost fields.
