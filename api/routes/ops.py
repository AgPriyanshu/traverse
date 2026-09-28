"""Health, cost and pipeline telemetry. Owned by devops engineer 1."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..contracts.api import (
    DeadLetterOut,
    HealthOut,
    MetricsOut,
    RoutingPolicyOut,
)
from ..contracts.pipeline import IngestionRunOut
from ..db.engine import get_session
from ..ops import gather_health, pipeline_status
from ..ops.answer_judge import AnswerJudgment, JudgeAnswerRequest, judge_answer
from ..ops.answer_quality import AnswerQualityOut, compute_answer_quality
from ..ops.extraction_cost import ExtractionCostOut, compute_extraction_cost
from ..ops.extraction_quality import ExtractionQualityOut, compute_extraction_quality
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
from ._stub import not_implemented

router = APIRouter(tags=["ops"])
OWNER = "do1"


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


@router.get("/ops/routing-policy", response_model=RoutingPolicyOut)
async def get_routing_policy() -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")


@router.put("/ops/routing-policy", response_model=RoutingPolicyOut)
async def set_routing_policy(body: RoutingPolicyOut) -> RoutingPolicyOut:
    not_implemented(OWNER, "S9.6")
