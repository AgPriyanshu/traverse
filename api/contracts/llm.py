"""Contracts for the LLM substrate. be2 owns the implementation from Sprint 2."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .enums import LLMPurpose

T = TypeVar("T")


class TokenBudget(BaseModel):
    """Prompt + items + room for the answer, against the model's context window."""

    max_context: int
    prompt_tokens: int
    output_reserve: int
    safety_margin: float = Field(default=0.9, gt=0.0, le=1.0)

    @property
    def item_budget(self) -> int:
        usable = int(self.max_context * self.safety_margin)

        return max(0, usable - self.prompt_tokens - self.output_reserve)


class BatchPlan(BaseModel, Generic[T]):
    """A batch that fits. ``was_split`` marks an item too large to send whole —
    it is split, never dropped, and the caller stitches the results back."""

    items: list[T]
    token_count: int
    was_split: bool = False


class LLMCallRecord(BaseModel):
    purpose: LLMPurpose
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    attempts: int = 1
    cached_prefix: bool | None = None
