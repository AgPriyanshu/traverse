"""Ablation configuration switching (S8.2, PRD F6.3).

One eval run sweeps several ``AblationConfig`` cells (PRD Appendix A: one
axis value held fixed against the recommended configuration of every other
axis, never the full cross product). This module is the one place a cell's
config turns into real runtime behaviour for the axes be2 owns — retrieval
and model. ``resolve`` is the entry point do1's S8.8 ablation runner calls
once per cell: it returns the concrete ``RetrievalMode``/``InferenceMode``
values to pass into ``api.query.retrieval.retrieve_for_narrative`` and
``api.query.generation.stream_narrative_draft`` (or ``api.llm.get_llm``/
``structured_call`` directly), not a shape the runner has to reverse-engineer
from ``AblationConfig``'s field names.

Recording the *input* ``AblationConfig`` — not this module's resolved output —
in ``EvalResult.config``/``EvalRun.config`` is what keeps a published number
reproducible from its own row: resolving is a pure function of the config, so
either one recovers the other.

The ``extraction`` axis (``extraction_mode``, ``alias_mode``,
``with_human_review``) has no switch here: it lives in ``api/pipeline/**``/
``api/extraction/**`` (be1) and the review gate (``api/review/**``), none of
which be2 owns or may edit (BRANCH.md). ``resolve`` raises
``AblationAxisNotOwned`` for it rather than silently returning "nothing to
switch" — a runner must not mistake that for "this axis has no effect".
"""

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
