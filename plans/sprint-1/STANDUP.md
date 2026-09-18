# Sprint 1 — standup

Three lines per agent per day: what landed, what is next, what is blocked.

## do1 · Day 2

- **Landed:** RabbitMQ is up at `pyamqp://guest:guest@localhost:5672//` with
  vhosts `/be1`, `/be2`, `/int` (be1 unblocked). Compose moved to the repo root
  with the full topology, behavioural healthchecks, `api/` and `web/`
  Dockerfiles, `nginx.conf` with `proxy_buffering off`, `.env.example`,
  `Makefile`, `scripts/**` and CI [S1.11–S1.15].
- **Next:** cold-start verification of the whole stack on shifted ports, then
  `make warm-models`.
- **Blocked on others:** `/health` still reports the freeze stub —
  `api/routes/ops.py` is not a do1 path, so the four-line wiring to
  `api.ops.gather_health` is filed in HANDOFF. `api/llm.py:49` still hardcodes a
  `/home/prinzz/...` cache path and breaks in every container.
