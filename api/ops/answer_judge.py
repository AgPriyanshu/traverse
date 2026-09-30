from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts.enums import LLMPurpose
from ..llm.structured import structured_call

JUDGE_PROMPT_VERSION = "answer_judge_v1"


class JudgeAnswerRequest(BaseModel):
    question_id: str
    question: str
    expected_answer: str | None = None
    expect_abstain: bool = False
    system_answer: str | None = None
    abstained: bool = False
    citations: list[dict] = Field(default_factory=list)


class AnswerJudgment(BaseModel):
    correct: bool = Field(
        description="True only if the system's answer conveys the same facts as "
        "the reference answer. A hedge that avoids being wrong without actually "
        "answering is not correct."
    )
    citation_supported: list[bool] = Field(
        default_factory=list,
        description="One entry per citation quote given, in order: does that "
        "quote, read in isolation, actually support the corresponding claim in "
        "the system's answer?",
    )
    reasoning: str = Field(description="One or two sentences explaining the verdict.")


def _format_citations(citations: list[dict]) -> str:
    if not citations:
        return "(none)"

    lines = []
    for i, citation in enumerate(citations):
        quote = citation.get("quote") or "(no quote)"
        page = citation.get("page_start")
        lines.append(f"  [{i}] page {page}: “{quote}”")

    return "\n".join(lines)


def build_prompt(
    *,
    question: str,
    expected_answer: str | None,
    expect_abstain: bool,
    system_answer: str | None,
    abstained: bool,
    citations: list[dict],
) -> str:
    """The versioned judge prompt (``answer_judge_v1``).

    Args:
        question: The gold question as asked.
        expected_answer: The gold reference answer, or ``None`` for an
            ``expect_abstain`` question.
        expect_abstain: Whether the gold set says the correct behaviour here
            is to decline to answer.
        system_answer: What the system under test actually said, if anything.
        abstained: Whether the system declined to answer.
        citations: The system's cited quotes, as
            ``[{"page_start": int, "quote": str}, ...]``.

    Returns:
        The full prompt text.
    """
    if expect_abstain:
        reference = (
            "This question has no correct factual answer in this novel -- the "
            "reference behaviour is to decline to answer (say the fact is not "
            "established), not to guess or hedge."
        )
    else:
        reference = f"Reference answer: {expected_answer}"

    return (
        "You are grading one question-answering system's response against a "
        "reference, for a tool that finds and cites facts in a novel. Judge "
        "only the facts asserted, not writing style or completeness of prose.\n\n"
        f"Question: {question}\n"
        f"{reference}\n\n"
        f"System's answer: "
        f"{system_answer if not abstained else '(the system declined to answer)'}\n\n"
        "Cited quotes (judge whether each supports the specific claim it is "
        "attached to in the system's answer, not the answer overall):\n"
        f"{_format_citations(citations)}\n\n"
        "Return your verdict as the given schema."
    )


async def judge_answer(
    *,
    question_id: str,
    question: str,
    expected_answer: str | None,
    expect_abstain: bool,
    system_answer: str | None,
    abstained: bool,
    citations: list[dict],
) -> AnswerJudgment:
    """Call the frontier judge for one question.

    Raises:
        PermanentLLMError: ``settings.inference_mode`` is ``local`` or no
            frontier model is configured (``api/llm/routing.py``) -- refused
            outright rather than silently judged by the local model.
    """
    prompt = build_prompt(
        question=question,
        expected_answer=expected_answer,
        expect_abstain=expect_abstain,
        system_answer=system_answer,
        abstained=abstained,
        citations=citations,
    )

    return await structured_call(
        prompt,
        AnswerJudgment,
        purpose=LLMPurpose.JUDGE,
        stage=f"answer_judge:{question_id}",
    )
