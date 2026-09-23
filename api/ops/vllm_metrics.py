"""Scrape vLLM's own Prometheus endpoint for prefix-cache and KV-cache stats.

Owned by devops engineer 1. PRD §5.2's pass-2 cost argument depends entirely
on the prefix cache actually hitting (character-graph.md, llm-runtime.md);
Sprint 4 needs to see this number live rather than discover a regression in
the retro (devops-1.md S3.15), so this is a first-class dashboard field this
sprint, not a Sprint 9 nice-to-have.

Deliberately a hand-rolled line parser, not a Prometheus client library:
``api/pyproject.toml`` is orchestrator-owned (frozen at the freeze), and a
handful of ``metric_name{...} value`` lines do not justify a new dependency
and the SCR that would take to add it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

METRICS_TIMEOUT_S = 3.0

# vLLM's own metric names (stable across the `--enable-prefix-caching`
# releases this project targets; see docker-compose.yml's vllm service args).
# A counter pair, not a single gauge, because the hit *rate* is a derived
# quantity over the observation window, not something vLLM reports directly.
_HITS_METRIC = "vllm:gpu_prefix_cache_hits_total"
_QUERIES_METRIC = "vllm:gpu_prefix_cache_queries_total"
_KV_USAGE_METRIC = "vllm:gpu_cache_usage_perc"

# vllm/vllm-openai:latest (the V1 engine) dropped the ``gpu_`` infix. S3.9's
# spike read the un-prefixed names off the real server, so reading only the old
# ones leaves the hit rate silently ``None`` on the image compose actually pulls.
_HITS_ALIASES = (_HITS_METRIC, "vllm:prefix_cache_hits_total")
_QUERIES_ALIASES = (_QUERIES_METRIC, "vllm:prefix_cache_queries_total")
_KV_USAGE_ALIASES = (_KV_USAGE_METRIC, "vllm:kv_cache_usage_perc")


def _first_present(totals: dict[str, float], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in totals:
            return totals[name]

    return None

_METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([0-9.eE+-]+)$"
)


def _parse_prometheus_text(body: str) -> dict[str, float]:
    """Sum every sample for each metric name, ignoring label sets.

    vLLM emits one series per metric with no labels that matter here (no
    per-model split when only one model is loaded); summing rather than
    taking "the first match" is defensive against a future multi-series
    export without silently under-counting.
    """
    totals: dict[str, float] = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE_RE.match(line.strip())
        if not match:
            continue
        name, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        totals[name] = totals.get(name, 0.0) + value

    return totals


@dataclass(frozen=True)
class VllmCacheStats:
    prefix_cache_hit_rate: float | None
    gpu_kv_cache_usage_pct: float | None


def _metrics_url(vllm_base_url: str) -> str:
    # settings.vllm_base_url is the OpenAI-compatible base (".../v1/"); the
    # Prometheus endpoint is unversioned, at the server root.
    root = vllm_base_url.split("/v1")[0].rstrip("/")

    return f"{root}/metrics"


async def fetch_vllm_cache_stats(vllm_base_url: str) -> VllmCacheStats | None:
    """Best-effort prefix-cache hit rate and KV-cache usage from vLLM.

    Returns ``None`` on any failure (vLLM not running, `INFERENCE_MODE=api`,
    a metrics-format change) -- a dashboard field going blank is a much
    smaller problem than an ops endpoint 500ing because a side metric server
    is unreachable.
    """
    url = _metrics_url(vllm_base_url)
    try:
        async with httpx.AsyncClient(timeout=METRICS_TIMEOUT_S) as client:
            response = await client.get(url)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        return None

    totals = _parse_prometheus_text(response.text)
    hits = _first_present(totals, _HITS_ALIASES)
    queries = _first_present(totals, _QUERIES_ALIASES)
    hit_rate = (hits / queries) if hits is not None and queries else None
    kv_usage = _first_present(totals, _KV_USAGE_ALIASES)

    return VllmCacheStats(
        prefix_cache_hit_rate=hit_rate, gpu_kv_cache_usage_pct=kv_usage
    )


@dataclass(frozen=True)
class VllmCacheCounters:
    hits: float
    queries: float


def hit_rate_between(
    before: VllmCacheCounters, after: VllmCacheCounters
) -> float | None:
    """Prefix-cache hit rate over the window between two counter snapshots.

    vLLM's counters are cumulative for the server's lifetime, so a single
    scrape is a blend of every run since it booted. Differencing two scrapes
    taken around one book's pass 2 is the only per-book number.
    """
    queries = after.queries - before.queries
    if queries <= 0:
        return None
    rate = (after.hits - before.hits) / queries

    return rate


async def fetch_vllm_cache_counters(vllm_base_url: str) -> VllmCacheCounters | None:
    """Raw cumulative prefix-cache counters, for ``hit_rate_between``."""
    url = _metrics_url(vllm_base_url)
    try:
        async with httpx.AsyncClient(timeout=METRICS_TIMEOUT_S) as client:
            response = await client.get(url)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        return None

    totals = _parse_prometheus_text(response.text)
    hits = _first_present(totals, _HITS_ALIASES)
    queries = _first_present(totals, _QUERIES_ALIASES)
    if hits is None or queries is None:
        return None

    return VllmCacheCounters(hits=hits, queries=queries)
