# Sprint 3 Retrospective

**Dates:** 2026-09-22 → 2026-09-23
**Goal:** upload *Pride and Prejudice*, get an accurate character roster, with the two Catherines in *Wuthering Heights* kept apart.
**Outcome:** Partially met. All stories are built and merged. The real-book extraction run and the quality numbers are not yet verified.

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
- A-3.5: Remaining SCRs: boto3 in pyproject/uv.lock, `MentionOut.span`, chunks `chapter_id` filter, `MetricsOut` cost fields.
