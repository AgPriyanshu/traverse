# ruff: noqa: E501
import asyncio
import logging
from uuid import UUID

from pydantic import BaseModel

from api.llm import structured_call

from ..contracts.enums import LLMPurpose
from ..graph import ontology

logger = logging.getLogger(__name__)

_PARALLEL = 16

# The verifier sees the quote alone, never the chunk, so it grades exactly what
# a reader clicking the citation would see. A claim the extractor made from
# surrounding context but the quote does not carry is a bad citation.
VERIFY_PROMPT = """Decide whether a quotation from a novel supports a claim about two characters.

Quotation: "{quote}"

Claim: {subject} is {predicate} {object}.
Meaning: {meaning}

Answer supported=true only if the quotation, read on its own, states or clearly implies this claim about exactly these two people, in this direction. If it is about other people, or only shows the two characters together, answer false.

Respond with JSON only: {{"supported": true or false}}
"""


class VerifyOutput(BaseModel):
    supported: bool


def _meaning(predicate: str) -> str:
    spec = ontology.spec_of(predicate)
    if spec.symmetric:
        text = f"{predicate} holds equally in both directions."
    else:
        text = f"the first person is the one described by {predicate} to the second."
    if spec.inverse and not spec.symmetric:
        text += f" (Its inverse is {spec.inverse}.)"

    return text


async def verify_claim(
    subject: str, predicate: str, obj: str, quote: str, *, book_id: UUID
) -> bool:
    """Ask the model whether ``quote`` alone supports the claim.

    Fails closed: any model error counts as unsupported, so an unavailable
    verifier can only cost recall, never admit a bad edge.
    """
    prompt = VERIFY_PROMPT.format(
        quote=quote.replace('"', "'"),
        subject=subject,
        predicate=predicate,
        object=obj,
        meaning=_meaning(predicate),
    )
    try:
        result = await structured_call(
            prompt,
            VerifyOutput,
            purpose=LLMPurpose.ADJUDICATE,
            book_id=str(book_id),
            stage="verify_relations",
        )
    except Exception:
        logger.warning("relation verification failed; treating as unsupported")

        return False

    return result.supported


async def verify_many(
    claims: list[tuple[str, str, str, str]], *, book_id: UUID
) -> list[bool]:
    """Verify claims concurrently, bounded here and by the shared LLM semaphore."""
    gate = asyncio.Semaphore(_PARALLEL)

    async def one(claim: tuple[str, str, str, str]) -> bool:
        async with gate:
            return await verify_claim(*claim, book_id=book_id)

    verdicts = await asyncio.gather(*(one(c) for c in claims))

    return list(verdicts)
