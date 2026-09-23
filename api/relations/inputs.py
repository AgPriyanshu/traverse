import importlib
import logging
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from . import repository

logger = logging.getLogger(__name__)

# be1 owns the prefilter (S4.10). Where it lands is settled in
# plans/sprint-4/HANDOFF.md; until then this probes the likely homes and falls
# back to the same rule computed locally from ``CharacterMention``.
_PREFILTER_HOMES = ("api.extraction.prefilter", "api.pipeline.prefilter")


async def candidate_chunk_ids(
    session: SQLModelAsyncSession, book_id: UUID
) -> tuple[set[UUID], str]:
    """Return the chunk ids pass 2 should read, and which source decided.

    Returns:
        ``(chunk ids, source)`` where source is ``"be1"`` or ``"local"``.
    """
    for module_name in _PREFILTER_HOMES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        function = getattr(module, "pass2_candidates", None)
        if function is None:
            continue

        refs = await function(book_id)
        ids = {
            getattr(ref, "chunk_id", None) or getattr(ref, "id", ref) for ref in refs
        }

        return ids, "be1"

    ids = await repository.chunks_with_two_characters(session, book_id)

    return ids, "local"
