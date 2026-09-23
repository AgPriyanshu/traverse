import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from . import repository

logger = logging.getLogger(__name__)


async def candidate_chunk_ids(
    session: SQLModelAsyncSession, book_id: UUID
) -> tuple[set[UUID], str]:
    """Return the chunk ids pass 2 should read, and which source decided.

    Prefers be1's prefilter (``api.pipeline.prefilter.pass2_candidates``, S4.10),
    which also keeps single-mention chunks whose scene has two participants.
    Falls back to the same distinct-character rule computed locally from
    ``CharacterMention`` when be1's module is not in this checkout.

    Returns:
        ``(chunk ids, source)`` where source is ``"be1"`` or ``"local"``.
    """
    try:
        from ..pipeline.prefilter import pass2_candidates
    except ImportError:
        logger.warning("api.pipeline.prefilter is absent; using the local prefilter")
        ids = await repository.chunks_with_two_characters(session, book_id)

        return ids, "local"

    refs = await pass2_candidates(book_id, session=session)
    ids = {ref.chunk_id for ref in refs}

    return ids, "be1"
