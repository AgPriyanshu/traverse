# Sprint N Retrospective

**Dates:** YYYY-MM-DD → YYYY-MM-DD
**Goal:** <the one-line sprint goal, copied from sprint-N/README.md>
**Outcome:** Met / Partially met / Missed

---

## 1. Delivered

| Story | Owner | Status | PRD ref | Notes |
|---|---|---|---|---|
| S N.1 | be1 | Done | F1.2 | |
| S N.2 | be2 | Carried to N+1 | F3.2 | blocked 1.5d on SCR-3 |

**Demo result:** Passed / Failed at step <n>.
Recording or command log: `<path>`

---

## 2. Metrics

| Metric | Target | Actual | Δ |
|---|---|---|---|
| Stories completed | | | |
| Merge-train conflicts | 0 | | |
| Blocking SCRs raised | ≤ 1 | | |
| Test suite runtime | | | |
| Integration run wall clock | | | |
| *Sprint-specific quality metric* | | | |

---

## 3. What went well

Be specific. "Good collaboration" is not a retro item; "freezing the Celery task
names as strings meant be2 never had to touch be1's `tasks.py`" is.

-

## 4. What went wrong

Name the mechanism, not the person. Every item here should answer "what would
have prevented this?"

-

## 5. What we learned

Things that were unknown at planning time — model behaviour, library limits,
cost or latency surprises, wrong assumptions in the PRD.

-

---

## 6. Action items

Every item needs an owner and a target sprint, and the next sprint's plan must
visibly absorb it. Items without both are deleted, not carried.

| # | Action | Owner | Target | Done? |
|---|---|---|---|---|
| A-N.1 | | | Sprint N+1 | |

**Carried from previous retro:**

| # | Action | Status |
|---|---|---|
| A-(N-1).x | | Done / Dropped (reason) |

---

## 7. PRD amendments

Anything this sprint proved wrong in `traverse-prd.md`. Edit the PRD, bump its
version, and record the change here — an out-of-date PRD is worse than none.

| Section | Change | Reason |
|---|---|---|
