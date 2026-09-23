import logging
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db.models import DocumentChunk
from .extract import ExtractedFact

logger = logging.getLogger(__name__)

_OFFSET_TOLERANCE = 2


async def attribute_speakers(
    session: SQLModelAsyncSession, book_id: UUID, facts: list[ExtractedFact]
) -> tuple[list[ExtractedFact], str]:
    """Replace the model's guessed speaker with be1's attribution where present.

    be1's speaker attribution (S4.9,
    ``api.pipeline.scene_repository.list_dialogue_lines``) resolves who said
    each dialogue line without asking the model twice. Where it has a resolved
    line covering a dialogue quote, its speaker wins over the model's
    ``asserted_by``. Otherwise the model's own guess stands, and a dialogue
    fact stays dialogue: an unresolved speaker still makes the edge hearsay.

    Returns:
        The facts, and ``"be1"`` or ``"model"`` for which source was available.
    """
    dialogue = [f for f in facts if f.assertion_type == "dialogue"]
    if not dialogue:
        return facts, "model"

    try:
        from ..pipeline.scene_repository import list_dialogue_lines
    except ImportError:
        logger.warning("scene_repository is absent; keeping the model's speakers")

        return facts, "model"

    lines = await list_dialogue_lines(session, book_id)
    chunk_ids = {f.chunk_id for f in dialogue}
    texts = dict(
        (
            await session.execute(
                select(DocumentChunk.id, DocumentChunk.text).where(
                    DocumentChunk.id.in_(chunk_ids)
                )
            )
        ).all()
    )
    by_chunk: dict[UUID, list] = {}
    for line in lines:
        if line.speaker_character_id is not None:
            by_chunk.setdefault(line.chunk_id, []).append(line)

    out = []
    for fact in facts:
        if fact.assertion_type == "dialogue":
            speaker = _speaker_for(fact, texts.get(fact.chunk_id, ""), by_chunk)
            if speaker is not None:
                fact = fact.model_copy(update={"asserted_by_id": speaker})
        out.append(fact)

    return out, "be1"


def _speaker_for(
    fact: ExtractedFact, text: str, by_chunk: dict[UUID, list]
) -> UUID | None:
    position = text.find(fact.quote)
    if position < 0:
        position = text.casefold().find(fact.quote.casefold())
    if position < 0:
        return None

    covering = [
        line
        for line in by_chunk.get(fact.chunk_id, [])
        if line.char_start - _OFFSET_TOLERANCE <= position and position < line.char_end
    ]
    if not covering:
        return None
    best = max(covering, key=lambda line: line.confidence)

    return best.speaker_character_id
