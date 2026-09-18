"""BGE cross-encoder reranker over the RRF-fused top 50, behind a flag.

PRD §5.1 calls the reranker "the largest single quality lever per unit
cost" — that claim is measured on the smoke set
(``api/tests/fixtures/retrieval_smoke.json``), not inherited; see
``plans/sprint-2/RETRO.md``.
"""

from functools import lru_cache
from uuid import UUID

from sentence_transformers import CrossEncoder

from ..config.settings import settings
from ..db.models.chunk_model import DocumentChunk

_DEFAULT_MODEL_ID = "BAAI/bge-reranker-v2-m3"

FusedResult = tuple[UUID, float, DocumentChunk, float | None, float | None]


def reranker_enabled() -> bool:
    """Whether the cross-encoder reranker runs, from settings.

    ``settings.reranker_enabled`` is pending SCR-2 (``plans/sprint-2/SCR.md``)
    — ``api/config/settings.py`` joined the orchestrator-owned list at this
    sprint's freeze. ``getattr`` with a ``False`` default means every call
    site here already does the right thing once the field lands, with no
    further change.
    """
    return bool(getattr(settings, "reranker_enabled", False))


@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    model_id = getattr(settings, "reranker_model_id", _DEFAULT_MODEL_ID)

    return CrossEncoder(model_id, max_length=512)


def rerank(query: str, fused: list[FusedResult]) -> list[FusedResult]:
    """Re-score ``fused`` with a cross-encoder over ``(query, chunk.text)``.

    The RRF score in each returned tuple is replaced with the cross-encoder
    score, so the caller's existing sort-and-slice keeps working unchanged;
    dense and lexical component scores pass through untouched — the chunk
    inspector still needs them regardless of which score ordered the list.

    Args:
        query: The original search query.
        fused: RRF-fused results, in any order.

    Returns:
        The same items, re-sorted by cross-encoder score, descending.
    """
    model = _model()
    pairs = [(query, chunk.text) for _id, _rrf, chunk, _dense, _lexical in fused]
    scores = model.predict(pairs)

    rescored: list[FusedResult] = [
        (chunk_id, float(score), chunk, dense_score, lexical_score)
        for (chunk_id, _rrf, chunk, dense_score, lexical_score), score in zip(
            fused, scores, strict=True
        )
    ]
    rescored.sort(key=lambda item: item[1], reverse=True)

    return rescored
