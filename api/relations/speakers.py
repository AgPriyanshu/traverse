import logging
from uuid import UUID

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from ..db import models
from ..db.models import DocumentChunk
from .extract import ExtractedFact
from .validator import fold

logger = logging.getLogger(__name__)


async def attribute_speakers(
    session: SQLModelAsyncSession, facts: list[ExtractedFact]
) -> tuple[list[ExtractedFact], str]:
    """Replace the model's guessed speaker with be1's attribution where present.

    be1's speaker attribution (S4.9) resolves who said each dialogue line
    without asking the model twice. Where it has a line covering a dialogue
    quote, its speaker wins over the model's ``asserted_by``. Where it has none,
    or its table is absent from this checkout, the model's own guess stands.

    Returns:
        The facts, and ``"be1"`` or ``"model"`` for which source was available.
    """
    line_model = getattr(models, "DialogueLine", None)
    dialogue = [f for f in facts if f.assertion_type == "dialogue"]
    if line_model is None or not dialogue:
        return facts, "model"

    chunk_ids = {f.chunk_id for f in dialogue}
    lines = (
        (
            await session.execute(
                select(line_model).where(line_model.chunk_id.in_(chunk_ids))
            )
        )
        .scalars()
        .all()
    )
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
    position = fold(text).find(fold(fact.quote))
    if position < 0:
        return None

    # ``fold`` preserves length for the characters lines are offset by, except
    # collapsed whitespace; offsets are therefore approximate, so nearest wins.
    candidates = [
        line
        for line in by_chunk.get(fact.chunk_id, [])
        if line.speaker_character_id is not None
        and line.char_start - 20 <= position <= line.char_end + 20
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda line: abs(line.char_start - position))

    return best.speaker_character_id
