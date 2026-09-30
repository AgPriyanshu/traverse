from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

Axis = Literal["extraction", "retrieval", "model"]

# Recorded verbatim in the published table so a cell that could not be run
# reads as "blocked: <reason>", never as a blank that looks like a zero.
BLOCKED_CONFIG_SWITCH = (
    "blocked: no ablation config-switch exists to run this configuration yet "
    "(F6.3/S8.2, be2 -- not landed as of this run); only the pipeline's single "
    "current configuration is measurable this sprint"
)
BLOCKED_FRONTIER_JUDGE = (
    "blocked: answer accuracy and citation precision are scored by a frontier "
    "LLM judge (api/ops/answer_judge.py, LLMPurpose.JUDGE) and no "
    "FRONTIER_MODEL/FRONTIER_API_KEY is configured in this environment -- see "
    "plans/sprint-8/HANDOFF.md"
)
BLOCKED_FRONTIER_MODEL = (
    "blocked: mode=api (frontier) requires settings.frontier_model, which is "
    "blank in this environment's .env -- api/llm/routing.py::route_for now "
    "raises PermanentLLMError for this cell (S8.2 wired InferenceMode through "
    "it, so the route itself exists; only the key is missing) -- see "
    "plans/sprint-8/HANDOFF.md"
)


@dataclass(frozen=True)
class AblationCell:
    """One row of one axis's sub-table."""

    axis: Axis
    label: str
    config: dict[str, Any]
    recommended: bool = False
    blocked_reason: str | None = None


RECOMMENDED_EXTRACTION: dict[str, Any] = {
    "extraction_mode": "two_pass",
    "alias_mode": "full_cascade",
    "with_human_review": False,
}
RECOMMENDED_RETRIEVAL: dict[str, Any] = {"retrieval_mode": "graph_constrained"}
RECOMMENDED_MODEL: dict[str, Any] = {"model_mode": "local"}


def build_matrix() -> list[AblationCell]:
    """The partial matrix this sprint runs (see module docstring)."""
    return [
        AblationCell(
            "extraction",
            "Single-pass, string-only aliases",
            {"extraction_mode": "single_pass", "alias_mode": "string_only", "with_human_review": False},
            blocked_reason=BLOCKED_CONFIG_SWITCH,
        ),
        AblationCell(
            "extraction",
            "Single-pass, full alias cascade",
            {"extraction_mode": "single_pass", "alias_mode": "full_cascade", "with_human_review": False},
            blocked_reason=BLOCKED_CONFIG_SWITCH,
        ),
        AblationCell(
            "extraction",
            "Two-pass, string-only aliases",
            {"extraction_mode": "two_pass", "alias_mode": "string_only", "with_human_review": False},
            blocked_reason=BLOCKED_CONFIG_SWITCH,
        ),
        AblationCell(
            "extraction",
            "Two-pass, full alias cascade (recommended)",
            dict(RECOMMENDED_EXTRACTION),
            recommended=True,
        ),
        AblationCell(
            "extraction",
            "Above + human review pass",
            {**RECOMMENDED_EXTRACTION, "with_human_review": True},
            blocked_reason=BLOCKED_CONFIG_SWITCH,
        ),
        AblationCell(
            "retrieval",
            "Vector only",
            {"retrieval_mode": "vector_only"},
        ),
        AblationCell(
            "retrieval",
            "Vector + BM25 hybrid",
            {"retrieval_mode": "bm25"},
        ),
        AblationCell(
            "retrieval",
            "+ rerank",
            {"retrieval_mode": "rerank"},
        ),
        AblationCell(
            "retrieval",
            "Graph-constrained + evidence hydration (recommended)",
            dict(RECOMMENDED_RETRIEVAL),
            recommended=True,
        ),
        AblationCell(
            "model",
            "Qwen3-8B local (recommended)",
            dict(RECOMMENDED_MODEL),
            recommended=True,
        ),
        AblationCell(
            "model",
            "Frontier API",
            {"model_mode": "frontier"},
            # Not statically blocked: api/llm/routing.py::route_for now has a
            # real frontier path (S8.2). scripts/run_ablation.py checks
            # settings.frontier_model at run time and reports
            # BLOCKED_FRONTIER_MODEL only when the key is actually absent.
        ),
        AblationCell(
            "model",
            "Routed (recommended per PRD; currently a placeholder, identical "
            "to local -- no per-purpose routing policy exists yet)",
            {"model_mode": "routed"},
        ),
    ]


def cache_key(cell: AblationCell, *, book_key: str, corpus_checksum: str, git_sha: str) -> str:
    """Key a cell's cached result on everything that could change its answer.

    Parsing/chunking/embedding are identical across most cells (S8.8's
    caching requirement) -- keying on the config fields plus the corpus
    checksum and git SHA means a cell is only ever recomputed when one of
    those actually changed, never on every invocation.
    """
    payload = {
        "axis": cell.axis,
        "config": cell.config,
        "book_key": book_key,
        "corpus_checksum": corpus_checksum,
        "git_sha": git_sha,
    }
    blob = json.dumps(payload, sort_keys=True).encode()

    return hashlib.sha256(blob).hexdigest()[:16]


def metrics_from_extraction_quality(payload: dict[str, Any]) -> dict[str, Any]:
    """Map ``GET /ops/extraction-quality`` onto the frozen ``MetricSet`` shape."""
    sample_size = (payload.get("roster_true_positives") or 0) + (
        payload.get("roster_false_negatives") or 0
    )

    return {
        "precision": payload.get("roster_precision"),
        "recall": payload.get("roster_recall"),
        "f1": payload.get("roster_f1"),
        "sample_size": sample_size,
    }


def metrics_from_relation_quality(payload: dict[str, Any]) -> dict[str, Any]:
    """Map ``GET /ops/relation-quality`` onto the frozen ``MetricSet`` shape."""
    return {
        "precision": payload.get("precision"),
        "recall": payload.get("recall"),
        "f1": payload.get("f1"),
        "sample_size": payload.get("scored_edges") or 0,
    }


def metrics_from_answer_quality(payload: dict[str, Any]) -> dict[str, Any]:
    """Map ``GET /ops/answer-quality`` onto the frozen ``MetricSet`` shape.

    ``accuracy`` and ``precision`` (read here as citation precision) are only
    populated once a run has been judged -- an unjudged partial run reports
    ``None`` for both rather than a misleading 0, matching the rate objects'
    own ``rate=None`` convention.
    """
    accuracy = payload.get("accuracy") or {}
    citation = payload.get("citation_precision") or {}

    return {
        "accuracy": accuracy.get("rate"),
        "precision": citation.get("rate"),
        "sample_size": payload.get("answered") or 0,
    }


def matrix_summary(cells: list[AblationCell]) -> dict[str, int]:
    """Honest accounting of the partial matrix -- how many cells of each axis
    exist versus how many can even be attempted before a run starts."""
    total = len(cells)
    blocked = sum(1 for c in cells if c.blocked_reason is not None)

    return {"total": total, "blocked": blocked, "runnable": total - blocked}
