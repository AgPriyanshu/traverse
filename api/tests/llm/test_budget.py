"""Property-style coverage for ``plan_batches``.

``hypothesis`` is not a project dependency (``api/pyproject.toml`` is
orchestrator-owned as of the Sprint 2 freeze — see BRANCH.md), so this drives
the same kind of check by hand: many randomly-sized inputs, fixed seed, exact
invariants checked every trial rather than sampled once.
"""

import random

import pytest
from transformers import AutoTokenizer

from api.config.settings import settings
from api.contracts.llm import TokenBudget
from api.llm.budget import plan_batches

pytestmark = pytest.mark.models

_WORDS = [
    "Elizabeth",
    "said",
    "the",
    "quick",
    "brown",
    "fox",
    "—",
    '"Hello,"',
    "chapter",
    "one",
    "reader,",
    "Darcy",
    "Bennet",
    "1815",
    "—and",
]


def _random_text(rng: random.Random, n_words: int) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(n_words))


def _tokenizer():
    return AutoTokenizer.from_pretrained(settings.llm_model)


def test_plan_batches_never_exceeds_budget_never_loses_an_item() -> None:
    tokenizer = _tokenizer()
    rng = random.Random(20260918)

    for _trial in range(25):
        n_items = rng.randint(1, 20)
        items = [_random_text(rng, rng.randint(1, 500)) for _ in range(n_items)]
        max_context = rng.choice([128, 256, 512, 1024])
        prompt_tokens = rng.randint(5, 30)
        output_reserve = rng.randint(5, 30)

        budget = TokenBudget(
            max_context=max_context,
            prompt_tokens=prompt_tokens,
            output_reserve=output_reserve,
        )
        item_budget = budget.item_budget

        if item_budget <= 0:
            continue

        plans = plan_batches(
            items,
            prompt_tokens=prompt_tokens,
            text_of=lambda item: item,
            max_context=max_context,
            output_reserve=output_reserve,
        )

        for plan in plans:
            assert plan.token_count <= item_budget

        original_tokens = sum(len(tokenizer.encode(item)) for item in items)
        planned_tokens = sum(plan.token_count for plan in plans)
        assert planned_tokens == original_tokens

        oversized = [
            item for item in items if len(tokenizer.encode(item)) > item_budget
        ]
        if oversized:
            assert any(plan.was_split for plan in plans)
        else:
            assert not any(plan.was_split for plan in plans)


def test_oversized_single_item_is_split_not_dropped() -> None:
    tokenizer = _tokenizer()
    huge = _random_text(random.Random(1), 5000)

    plans = plan_batches(
        [huge],
        prompt_tokens=50,
        text_of=lambda item: item,
        max_context=256,
        output_reserve=20,
    )

    assert len(plans) > 1
    assert all(plan.was_split for plan in plans)
    assert sum(plan.token_count for plan in plans) == len(tokenizer.encode(huge))


def test_exhausted_budget_raises() -> None:
    with pytest.raises(ValueError, match="item_budget"):
        plan_batches(
            ["anything"],
            prompt_tokens=900,
            text_of=lambda item: item,
            max_context=1000,
            output_reserve=200,
        )


def test_small_items_pack_into_one_batch() -> None:
    plans = plan_batches(
        ["one", "two", "three"],
        prompt_tokens=10,
        text_of=lambda item: item,
        max_context=1024,
        output_reserve=10,
    )

    assert len(plans) == 1
    assert len(plans[0].items) == 3
    assert plans[0].was_split is False
