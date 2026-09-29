"""Health, cost and pipeline telemetry. Owned by devops engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    CostBreakdown,
    DeadLetterOut,
    EvalRunOut,
    HealthOut,
    MetricsOut,
    RoutingPolicyOut,
)
from ..contracts.enums import LLMPurpose
from ..contracts.pipeline import IngestionRunOut
from ..db.engine import get_session
from ..llm import routing as llm_routing
from ..llm.policy_repository import (
    DEFAULT_PURPOSES,
    get_current_policy,
    write_new_policy,
)
from ..ops import gather_health, pipeline_status
from ..ops.ablation import get_eval_run, get_latest_eval_run
from ..ops.answer_judge import AnswerJudgment, JudgeAnswerRequest, judge_answer
from ..ops.answer_quality import AnswerQualityOut, compute_answer_quality
from ..ops.budget_guard import BudgetStatusOut, compute_budget_status
from ..ops.cost_telemetry import (
    compute_cost_breakdown,
    list_cost_snapshots,
    rolling_window,
    save_cost_snapshot,
)
from ..ops.extraction_cost import ExtractionCostOut, compute_extraction_cost
from ..ops.extraction_quality import ExtractionQualityOut, compute_extraction_quality
from ..ops.performance_telemetry import PerformanceOut, compute_performance
from ..ops.pipeline_health import PipelineHealthOut, compute_pipeline_health
from ..ops.query_latency import QueryLatencyOut, compute_query_latency
from ..ops.reconciliation_quality import (
    ReconciliationQualityOut,
    compare_graph_checksums,
    compute_reconciliation_quality,
)
from ..ops.relation_cost import RelationCostOut, compute_relation_cost
from ..ops.relation_quality import RelationQualityOut, compute_relation_quality
from ..ops.review_metrics import (
    DEFAULT_QUEUE_DEPTH_THRESHOLD,
    STALE_TASK_AGE_HOURS,
    ReviewAlertsOut,
    ReviewMetricsOut,
    compute_review_alerts,
    compute_review_metrics,
)

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthOut, tags=["ops"])
async def health() -> HealthOut:
    """Liveness plus per-dependency status.

    Real probes as of S1.12 (``api/ops/probes.py``, do1) — concurrent, 5s
    timeout each. ``llm`` never gates the overall status: the default profile
    has no GPU (PRD NFR-deploy).
    """
    return await gather_health()


@router.get("/ops/metrics", response_model=MetricsOut)
async def metrics(
    book_id: UUID | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> MetricsOut:
    """Per-stage cost and timing (S2.17). ``prefix_cache_hit_rate`` is live from
    vLLM as of S3.15 (``api/ops/vllm_metrics.py``) when running local inference."""
    return await pipeline_status.get_metrics(session, book_id=book_id)


@router.get("/ops/cost-breakdown", response_model=CostBreakdown)
async def cost_breakdown(
    window: str = Query(default="daily", pattern="^(daily|monthly)$"),
    persist: bool = Query(default=False),
    session: SQLModelAsyncSession = Depends(get_session),
) -> CostBreakdown:
    """Rolling cost by stage and by purpose, plus query/book counts (S9.1, F7.1).

    ``window=daily`` is the last 24h, ``window=monthly`` the last 30 days --
    both always computed live from ``IngestionStage``/``QueryLog``, never from
    a stale snapshot. ``persist=true`` additionally writes the result to
    ``cost_snapshot`` so ``GET /ops/cost-snapshots`` has a point to plot; a
    plain read never has that side effect on its own.
    """
    days = 1 if window == "daily" else 30
    window_start, window_end = rolling_window(days=days)
    result = await compute_cost_breakdown(
        session, window_start=window_start, window_end=window_end
    )
    if persist:
        await save_cost_snapshot(session, result)
    return result


@router.get("/ops/cost-snapshots", response_model=list[CostBreakdown])
async def cost_snapshots(
    limit: int = Query(default=90, le=365),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[CostBreakdown]:
    """Stored cost-snapshot history, newest first -- the rolling-spend chart's feed."""
    rows = await list_cost_snapshots(session, limit=limit)
    return [
        CostBreakdown(
            window_start=row.window_start,
            window_end=row.window_end,
            total_cost_usd=row.total_cost_usd,
            by_stage=row.by_stage,
            by_purpose=row.by_purpose,
            query_count=row.query_count,
            book_count=row.book_count,
        )
        for row in rows
    ]


@router.get("/ops/performance", response_model=PerformanceOut)
async def performance(
    book_id: UUID | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> PerformanceOut:
    """Stage latency percentiles, ingestion throughput, GPU/KV pressure,
    Celery queue depth and prefix-cache hit rate in one screen (S9.2, F7.2).

    Pure presentation over data every stage has written since Sprint 2 --
    see ``api/ops/performance_telemetry.py`` for what each field reads.
    """
    return await compute_performance(session, book_id=book_id)


@router.get("/ops/pipeline-health", response_model=PipelineHealthOut)
async def pipeline_health(
    book_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    session: SQLModelAsyncSession = Depends(get_session),
) -> PipelineHealthOut:
    """Run history, per-stage failure rate, retry outcomes and dead-letter,
    each with a trace link (S9.3, F7.4) -- "what broke and where" on one screen.
    """
    return await compute_pipeline_health(session, book_id=book_id, limit=limit)


@router.get("/ops/budget-status", response_model=BudgetStatusOut)
async def budget_status(
    session: SQLModelAsyncSession = Depends(get_session),
) -> BudgetStatusOut:
    """Monthly spend vs. the configured budget cap (S9.4, §9.1).

    Visibility only from this route; ``scripts/budget_monitor.py`` is what
    acts on a breach (pausing ``celery-worker``) so a public deploy degrades
    rather than running up an unbounded bill.
    """
    return await compute_budget_status(session)


@router.get("/ops/extraction-quality", response_model=ExtractionQualityOut)
async def extraction_quality(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ExtractionQualityOut:
    """Roster P/R/F1, B3, tier accuracy, rejection precision (S3.14).

    Informational only this sprint — a regression gate lands in Sprint 8
    (F6.4). Returns ``gold_available=False`` for any book without a labelled
    gold set (``eval/gold/**``); today that is every book except Pride and
    Prejudice and Wuthering Heights (S3.13).
    """
    return await compute_extraction_quality(session, book_id)


@router.get("/ops/extraction-cost", response_model=ExtractionCostOut)
async def extraction_cost(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ExtractionCostOut:
    """Tokens, cost at both rates, and wall clock/100 pages for pass 1 (S3.15).

    Prefix-cache hit rate and KV-cache usage are read live from vLLM when
    ``INFERENCE_MODE=local``; ``None`` under ``INFERENCE_MODE=api`` since
    there is no local cache to report on.
    """
    return await compute_extraction_cost(session, book_id)


@router.get("/ops/relation-quality", response_model=RelationQualityOut)
async def relation_quality(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> RelationQualityOut:
    """Per-predicate P/R/F1, spurious and direction rates, temporal arcs (S4.14).

    Also reports the evidence-free edge count, which must be 0 whether or not
    the book has gold relations. ``gold_available=False`` for an unlabelled book.
    """
    return await compute_relation_quality(session, book_id)


@router.get("/ops/relation-cost", response_model=RelationCostOut)
async def relation_cost(
    book_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> RelationCostOut:
    """Pass-2 tokens, chunks skipped, wall clock, USD and cache hit rate (S4.15).

    ``prefix_cache_alert`` is set when a measured hit rate is below 80%.
    """
    return await compute_relation_cost(session, book_id)


@router.get("/ops/answer-quality", response_model=AnswerQualityOut)
async def answer_quality(book_key: str = Query(...)) -> AnswerQualityOut:
    """Accuracy, citation precision, abstention rate, aggregation exact-match (S6.14).

    Reads no live table -- scores whatever ``scripts/eval_answers.py`` last
    wrote to ``eval/gold/<book>/answer_judgements.json`` against the gold
    question set. ``gold_available=False`` for a book with no labelled
    question set; ``answered=0`` (not an error) for one that has never been
    run, e.g. because be2's query pipeline (S6.1-S6.5) has not merged yet.
    """
    return compute_answer_quality(book_key)


@router.post("/ops/judge-answer", response_model=AnswerJudgment)
async def judge_answer_route(body: JudgeAnswerRequest) -> AnswerJudgment:
    """Frontier-model judge for one answered question (S6.14).

    Never the model under test — ``LLMPurpose.JUDGE`` always routes to
    ``settings.frontier_model`` (``api/llm/routing.py``), refusing outright
    under ``INFERENCE_MODE=local`` rather than grading with the local model.
    """
    return await judge_answer(
        question_id=body.question_id,
        question=body.question,
        expected_answer=body.expected_answer,
        expect_abstain=body.expect_abstain,
        system_answer=body.system_answer,
        abstained=body.abstained,
        citations=body.citations,
    )


@router.get("/ops/query-latency", response_model=QueryLatencyOut)
async def query_latency(
    project_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> QueryLatencyOut:
    """p50/p95/p99 latency and TTFT against the NFR-perf budget (S6.15).

    ``sample_count=0`` until be2's query pipeline (S6.1-S6.5) starts writing
    ``QueryLog`` rows -- not an error, and not a passing gate either
    (``p95_within_budget=None``). Judge only from the integration host
    (BRANCH.md §9); vLLM is a single-GPU host singleton every worktree
    shares.
    """
    return await compute_query_latency(session, project_id)


@router.get("/ops/reconciliation-quality", response_model=ReconciliationQualityOut)
async def reconciliation_quality(
    project_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ReconciliationQualityOut:
    """Cross-book link P/R, false-merge rate and duplicate rate (S5.14).

    Also reports a deterministic ``graph_checksum`` of the project's
    character/relation set, independent of the gold set's availability --
    the order-independence check (`eval/runners/reconciliation.py
    --compare-project-id`) only needs two projects' checksums to compare.
    ``gold_available=False`` for a project whose books don't match a known
    series, or a series without a labelled gold set yet.
    """
    return await compute_reconciliation_quality(session, project_id)


@router.get("/ops/reconciliation-order-check")
async def reconciliation_order_check(
    project_id: UUID = Query(...),
    compare_project_id: UUID = Query(...),
    session: SQLModelAsyncSession = Depends(get_session),
) -> dict:
    """Hard pass/fail: do two projects' graphs hash identically (S5.14)?

    Intended for a forward-order project and a reverse-order project ingesting
    the same series -- the Sprint 5 DoD's "reverse-order upload produces a
    checksum-identical graph" claim, made checkable rather than eyeballed.
    """
    identical = await compare_graph_checksums(session, project_id, compare_project_id)

    return {
        "project_id": str(project_id),
        "compare_project_id": str(compare_project_id),
        "checksums_identical": identical,
    }


@router.get("/ops/review-metrics", response_model=ReviewMetricsOut)
async def review_metrics(
    project_id: UUID | None = Query(default=None),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ReviewMetricsOut:
    """Queue depth, task age, time-to-resolve, outcome mix, correction rate (S7.11).

    Correction rate is grouped by pipeline stage, not raw task type -- a
    stage humans correct 40% of the time is a quality problem the automated
    metrics miss, and it points Sprint 8's calibration at the right target.
    """
    return await compute_review_metrics(session, project_id=project_id)


@router.get("/ops/review-alerts", response_model=ReviewAlertsOut)
async def review_alerts(
    project_id: UUID | None = Query(default=None),
    queue_depth_threshold: int = Query(default=DEFAULT_QUEUE_DEPTH_THRESHOLD),
    stale_after_hours: int = Query(default=STALE_TASK_AGE_HOURS),
    session: SQLModelAsyncSession = Depends(get_session),
) -> ReviewAlertsOut:
    """Queue-depth, stale-task and orphaned-graph-thread alerts (S7.11).

    An orphaned thread is a graph paused on an interrupt with no open review
    task pointing at it -- a state leak, and a silent one until this catches it.
    """
    return await compute_review_alerts(
        session,
        project_id=project_id,
        queue_depth_threshold=queue_depth_threshold,
        stale_after_hours=stale_after_hours,
    )


@router.get("/ops/pipeline/runs", response_model=list[IngestionRunOut])
async def pipeline_runs(
    book_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[IngestionRunOut]:
    """Most recent ingestion runs, newest first, each with its stages and trace."""
    return await pipeline_status.list_runs(session, book_id=book_id, limit=limit)


@router.get("/ops/pipeline/dead-letter", response_model=list[DeadLetterOut])
async def dead_letter(
    session: SQLModelAsyncSession = Depends(get_session),
) -> list[DeadLetterOut]:
    """Every book whose latest run has a stage currently `failed`."""
    return await pipeline_status.list_dead_letters(session)


@router.get("/ops/eval-runs/latest", response_model=EvalRunOut)
async def eval_run_latest(
    session: SQLModelAsyncSession = Depends(get_session),
) -> EvalRunOut:
    """The most recent ablation run written by ``scripts/run_ablation.py`` (S8.8).

    404 rather than an empty/zeroed body when no run has ever been recorded —
    "no ablation has run yet" and "the last ablation scored zero" must not
    look the same to a caller.
    """
    run = await get_latest_eval_run(session)
    if run is None:
        raise HTTPException(status_code=404, detail="no eval run recorded yet")

    return run


@router.get("/ops/eval-runs/{run_id}", response_model=EvalRunOut)
async def eval_run_by_id(
    run_id: UUID,
    session: SQLModelAsyncSession = Depends(get_session),
) -> EvalRunOut:
    """One ablation run by id, for a drill-down link off the latest table."""
    run = await get_eval_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eval run not found")

    return run


@router.get("/ops/routing-policy", response_model=RoutingPolicyOut)
async def get_routing_policy(
    session: SQLModelAsyncSession = Depends(get_session),
) -> RoutingPolicyOut:
    """The live per-purpose model policy (S9.6, F7.3) -- the max-version row.

    Also re-syncs this process's in-memory routing cache
    (``api/llm/routing.py::route_for`` reads it, not this table directly)
    from Postgres, so a read from a process that did not make the last PUT
    -- a fresh API server restart, a Celery worker -- still reflects the
    persisted policy rather than the hardcoded local-only defaults.

    Returns ``version=0`` with the synthesized defaults when no PUT has ever
    landed, so a caller always gets a well-defined "current policy" rather
    than a 404 or an empty body.
    """
    current = await get_current_policy(session)
    if current is None:
        return RoutingPolicyOut(version=0, purposes=dict(DEFAULT_PURPOSES))

    llm_routing.set_live_policy(current.version, current.purposes)
    return RoutingPolicyOut(version=current.version, purposes=current.purposes)


@router.put("/ops/routing-policy", response_model=RoutingPolicyOut)
async def set_routing_policy(
    body: RoutingPolicyOut,
    session: SQLModelAsyncSession = Depends(get_session),
) -> RoutingPolicyOut:
    """Append the next policy version and flip this process's live routing
    immediately (S9.6, F7.3) -- the closing-argument demo needs the very next
    query answered on this same server to visibly use the new mapping.

    ``body.version`` is ignored: the version is the audit trail's own
    sequence number, assigned server-side from the current max, never
    client-supplied (migration 0012 -- every PUT is a new row).
    """
    unknown = sorted(set(body.purposes) - {purpose.value for purpose in LLMPurpose})
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown purpose(s): {unknown}")

    row = await write_new_policy(session, body.purposes)
    llm_routing.set_live_policy(row.version, row.purposes)

    return RoutingPolicyOut(version=row.version, purposes=row.purposes)
