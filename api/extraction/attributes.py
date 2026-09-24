"""Character attribute extraction (S3.5, F2.3).

Every attribute must carry a page citation or it is not stored — the same
rule ``graph.upsert`` enforces for relation evidence one level up
(``api/AGENTS.md``).
"""

import logging
from uuid import UUID

from ..contracts.enums import LLMPurpose
from ..llm import LengthLimitError, structured_call
from .prompts import ATTRIBUTE_PROMPT
from .schemas import AttributesOutput

logger = logging.getLogger(__name__)

# Enough contexts to ground occupation/age/family-role/description without
# sending a busy protagonist's entire mention history through the model.
_MAX_CONTEXTS = 12


async def extract_attributes(
    name: str, contexts: list[dict], *, book_id: UUID
) -> dict[str, dict]:
    """Extract grounded attributes for one resolved character.

    Args:
        name: The character's canonical name.
        contexts: Its merged context entries (``page``, ``context``).
        book_id: Tags the Langfuse trace.

    Returns:
        ``attribute key -> {"value", "page", "quote"}`` for every attribute
        whose cited page is one this character was actually seen on — a page
        the model invents is dropped rather than trusted.
    """
    if not contexts:
        return {}

    valid_pages = {c["page"] for c in contexts}
    top = sorted(contexts, key=lambda c: c["page"])[:_MAX_CONTEXTS]
    passages = "\n".join(f"(page {c['page']}) {c['context']}" for c in top)
    prompt = ATTRIBUTE_PROMPT.format(name=name, passages=passages)

    try:
        result = await structured_call(
            prompt,
            AttributesOutput,
            purpose=LLMPurpose.CHARACTER_EXTRACT,
            book_id=str(book_id),
            stage="resolve_aliases",
        )
    except LengthLimitError:
        # Attributes are enrichment. A runaway reply for one character (a
        # 634-token prompt once produced 6144 tokens on Wuthering Heights)
        # must not fail the whole stage and lose the roster.
        logger.warning(
            "book %s: attribute extraction for %r overflowed the length limit; "
            "storing no attributes for it",
            book_id,
            name,
        )

        return {}

    attributes: dict[str, dict] = {}
    for item in result.attributes:
        if item.page not in valid_pages:
            logger.warning(
                "book %s: dropping attribute %r for %r cited to page %s, which "
                "is not one of its own contexts",
                book_id,
                item.key,
                name,
                item.page,
            )
            continue

        attributes[item.key] = {
            "value": item.value,
            "page": item.page,
            "quote": item.quote,
        }

    return attributes
