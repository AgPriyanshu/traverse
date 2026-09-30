from dataclasses import dataclass

from ..contracts.api import AblationConfig
from ..contracts.enums import InferenceMode
from ..retrieval import RetrievalMode

_MODEL_MODE_TO_INFERENCE_MODE: dict[str, InferenceMode] = {
    "local": InferenceMode.LOCAL,
    "frontier": InferenceMode.API,
    "routed": InferenceMode.ROUTED,
}


class AblationAxisNotOwned(Exception):
    """The requested axis has no runtime switch in api/query, api/graph,
    api/relations or api/llm — see this module's docstring."""


@dataclass(frozen=True)
class ResolvedAblation:
    """What one ``AblationConfig`` cell resolves to, for the axes be2 owns.

    A cell is one axis value at a time (PRD Appendix A), so exactly one of
    the two fields is non-``None`` for a resolvable config; both are ``None``
    when neither axis applies to it. Pass ``retrieval_mode`` to
    ``retrieve_for_narrative``/``hybrid_search``, ``inference_mode`` to
    ``stream_narrative_draft``/``get_llm``/``structured_call``.
    """

    retrieval_mode: RetrievalMode | None
    inference_mode: InferenceMode | None


def resolve(config: AblationConfig) -> ResolvedAblation:
    """Turn one ablation cell's config into the runtime switches be2 owns.

    Args:
        config: One ``AblationConfig`` cell (``api/contracts/api.py``).

    Returns:
        The concrete ``RetrievalMode``/``InferenceMode`` this cell measures.
        Both ``None`` when ``config.axis`` is neither ``"retrieval"`` nor
        ``"model"`` — the recommended-configuration default applies, i.e.
        pass ``None`` straight through to the functions above, which already
        default to today's production behaviour.

    Raises:
        AblationAxisNotOwned: ``config.axis == "extraction"``. Extraction
            pass count, alias cascade depth, and the human-review gate need a
            switch in ``api/pipeline``/``api/extraction`` (be1) or
            ``api/review``; none are be2-owned. See
            ``plans/sprint-8/HANDOFF.md``.
    """
    if config.axis == "extraction":
        raise AblationAxisNotOwned(
            "axis='extraction' has no runtime switch in api/query, api/graph, "
            "api/relations or api/llm. extraction_mode/alias_mode need a "
            "switch in api/pipeline or api/extraction (be1-owned); "
            "with_human_review needs one in api/review. Neither is be2's to "
            "build (BRANCH.md file ownership) — see plans/sprint-8/HANDOFF.md."
        )

    retrieval_mode = None
    if config.axis == "retrieval" and config.retrieval_mode is not None:
        retrieval_mode = RetrievalMode(config.retrieval_mode)

    inference_mode = None
    if config.axis == "model" and config.model_mode is not None:
        inference_mode = _MODEL_MODE_TO_INFERENCE_MODE[config.model_mode]

    return ResolvedAblation(
        retrieval_mode=retrieval_mode, inference_mode=inference_mode
    )
