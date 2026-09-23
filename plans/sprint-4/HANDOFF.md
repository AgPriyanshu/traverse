
## do1 -> be2, be1, orchestrator

### S4.14 relation quality

- `make eval-relations BOOK=pride-and-prejudice` prints the table
  (per-predicate P/R/F1, spurious rate, direction accuracy, temporal arcs,
  citation accuracy, evidence-free counts, pass-2 cost). Backed by
  `GET /ops/relation-quality?book_id=` and `GET /ops/relation-cost?book_id=`.
- Gold: `eval/gold/pride_and_prejudice/relations.yaml`, 33 relations over the
  12 protagonist/major characters, pinned to the corpus checksum, closed world
  over in-scope pairs (`ignored_predicates` are exempt). Four temporal arcs
  (Elizabeth/Darcy, Jane/Bingley, Collins/Lucas, Wickham/Lydia). Chapter labels
  were read from the public text and are approximate; scoring tolerance is 3
  chapters. Relationships outside the ontology (aunt, cousin, patron) are not
  labelled. **Wuthering Heights is not labelled yet.**
- Matching is after inverse normalisation, so be2 may emit `child_of` or
  `parent_of`; a reversed pair is a direction error and a strict miss.
- Citation accuracy: `make judge-citations BOOK=pride-and-prejudice` (50
  seeded samples, resumable), writes `citation_judgements.json`. It needs
  `GET /relations/{id}/evidence` (S4.7) and the graph route live. **Not yet
  judged; the 95% number does not exist yet.**
- Evidence-free edges are checked in Postgres and Neo4j; the PR workflow and
  nightly fail if either is non-zero.

### S4.15 cost and rebuild

- be2: the drill calls the Celery task `graph.upsert` with `(book_id,)` and
  expects it to be idempotent, standalone (no ingestion run required) and to
  clear `stale`. Wall clock includes the task. `relations.extract` must set
  `rows_written` to chunks sent to the model (see SCR-14).
- `make graph-rebuild BOOK=<key>`, `make graph-rebuild-drill` (synthetic graph,
  wired into `make test-integration`). The drill refuses to pass on an empty
  graph.
- The nightly posts pass-2 cost, appends `pass2-cost-trend.jsonl` and fails on
  a cache hit rate under 80%.
- **Fixed a latent bug:** `api/ops/vllm_metrics.py` read only the pre-V1
  `vllm:gpu_prefix_cache_*` names; be2's S3.9 spike saw the unprefixed ones, so
  the hit rate was probably always `None`. Both are read now.

### Carried items

- `test` image tag: `TEST_IMAGE_TAG` (compose default falls back to
  `TRAVERSE_TAG`), set by make to the worktree directory name and by `make env`
  into `.env`. For bare compose: `TEST_IMAGE_TAG=$(basename $PWD)`.
- vLLM cache path: mounted at `/models` with `HF_HOME=/models/huggingface`.
  Not verified on a GPU cold start.
- `make ingest BOOK=<key>` (`scripts/ingest_book.py`): reuses a ready book,
  otherwise uploads and polls.
- Docker credentials: make now sets `DOCKER_CONFIG` to `.docker-nocreds/`
  (`{}`) when `docker-credential-desktop.exe` fails; `NOCREDS=0/1` overrides.
  See infra-topology.md.

### Incident to know about

Running `docker compose --profile test run` from this worktree recreated the
shared `db` and `rabbitmq` containers (compose config drift against the running
stack); they came back healthy within about a minute with volumes intact.
Anyone mid-run around that time may have seen a dropped connection.
