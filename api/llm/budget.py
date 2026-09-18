"""Assemble items into batches that fit the model's context window.

Counts with the model's own tokenizer rather than a characters/4 estimate;
prose with dialogue and em-dashes tokenizes differently from the estimate and
the error compounds across a batch into a context overflow (PRD §5.2).
"""

from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import TypeVar, cast

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from ..config.settings import settings
from ..contracts.llm import BatchPlan, TokenBudget

T = TypeVar("T")


@lru_cache(maxsize=2)
def _tokenizer(model_id: str) -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(model_id)


def plan_batches(
    items: Sequence[T],
    *,
    prompt_tokens: int,
    text_of: Callable[[T], str],
    max_context: int,
    output_reserve: int,
    safety_margin: float = 0.9,
    tokenizer_model: str | None = None,
) -> list[BatchPlan[T]]:
    """Group ``items`` into batches that fit the model's context window.

    Items are packed greedily in order, in one pass. An item too large to fit
    the per-item budget on its own is split on token boundaries rather than
    dropped or sent oversized; the caller stitches split pieces back together
    using ``BatchPlan.was_split``. A split piece is represented as decoded
    text — callers that batch anything other than plain text should treat
    ``T`` as ``str`` for split pieces.

    Args:
        items: Items to batch, in the order they should be sent.
        prompt_tokens: Tokens the fixed instruction prompt costs, counted once
            per batch since it is sent with every batch.
        text_of: Extracts the text of one item, for tokenization.
        max_context: The model's context window, in tokens.
        output_reserve: Tokens held back for the structured response.
        safety_margin: Fraction of ``max_context`` actually usable, to absorb
            tokenizer drift between this count and the server's.
        tokenizer_model: Model whose tokenizer counts tokens. Defaults to
            ``settings.llm_model`` — the model actually being budgeted for.

    Returns:
        Batch plans covering every item exactly once, in order.

    Raises:
        ValueError: ``prompt_tokens`` and ``output_reserve`` alone already
            exceed the usable context, so no item could ever fit.
    """
    budget = TokenBudget(
        max_context=max_context,
        prompt_tokens=prompt_tokens,
        output_reserve=output_reserve,
        safety_margin=safety_margin,
    )
    item_budget = budget.item_budget

    if item_budget <= 0:
        raise ValueError(
            "prompt_tokens + output_reserve leaves no room for items "
            f"(item_budget={item_budget})"
        )

    tokenizer = _tokenizer(tokenizer_model or settings.llm_model)

    plans: list[BatchPlan[T]] = []
    current_items: list[T] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_items, current_tokens

        if current_items:
            plans.append(BatchPlan(items=current_items, token_count=current_tokens))

        current_items = []
        current_tokens = 0

    for item in items:
        token_ids = tokenizer.encode(text_of(item))

        if len(token_ids) > item_budget:
            flush()

            for start in range(0, len(token_ids), item_budget):
                piece_ids = token_ids[start : start + item_budget]
                piece_text = tokenizer.decode(piece_ids)
                plans.append(
                    BatchPlan(
                        items=[cast(T, piece_text)],
                        token_count=len(piece_ids),
                        was_split=True,
                    )
                )

            continue

        if current_tokens + len(token_ids) > item_budget:
            flush()

        current_items.append(item)
        current_tokens += len(token_ids)

    flush()

    return plans
