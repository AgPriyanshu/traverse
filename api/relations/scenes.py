from uuid import UUID

from ..db.models import DocumentChunk
from ..pipeline.scene_repository import SceneRow

MIN_SCENE_MENTIONS = 2


def build_reading_chunks(
    chunks: list[tuple[DocumentChunk, int | None]],
    scenes: list[SceneRow],
) -> tuple[
    list[tuple[DocumentChunk, int | None]], dict[UUID, int], dict[UUID, tuple[UUID, ...]]
]:
    """Merge each scene's member chunks into one pass-2 reading unit.

    Sprint 4's recall audit found the median chunk on Pride and Prejudice is
    60 characters -- most "chunks" are a single clause, and a clause that
    refers to a character by pronoun only ("he had the means of exercising
    it") carries no roster mention of its own no matter who "he" is. Reading
    one in isolation gives the extractor nothing to resolve the pronoun
    against and gives the validator no chunk text to confirm an endpoint
    against even when the model gets it right from broader context. A scene
    (be1's own grouping) is the natural larger reading unit: its member
    chunks already cohere around one continuous passage, and
    ``scene_participant`` already counts exactly the distinct-roster-mention
    signal the prefilter uses, just scene-wide instead of chunk-wide.

    A merged unit's ``id`` is reused from its first member chunk. Evidence
    citation keys off page numbers and the quote text (``page_refs``,
    ``EvidenceItem``), never ``chunk_id`` directly, so pointing every fact at
    the scene's lead chunk for the foreign key is a citation-accurate
    simplification, not a provenance loss -- the cited page range still spans
    the whole scene and the quote itself is unchanged.

    Args:
        chunks: The book's chunks in document order, paired with chapter
            numbers, as returned by
            ``pipeline.repository.list_chunks_with_chapter_number``.
        scenes: The book's scenes, as returned by
            ``pipeline.scene_repository.list_scenes``.

    Returns:
        ``(units, mentions, members)`` where ``units`` is the whole book
        re-expressed at reading-unit granularity (one entry per scene, plus a
        singleton entry for any chunk no scene claims), in document order;
        ``mentions`` maps each unit's id to the distinct roster characters
        its whole scene names -- ``-1`` for a singleton, meaning "no scene
        covers this chunk; fall back to the caller's own chunk-level rule";
        and ``members`` maps each unit's id to the raw chunk ids it merges,
        for reporting true chunk coverage alongside the unit count.
    """
    by_id = {chunk.id: (chunk, chapter) for chunk, chapter in chunks}
    covered: set[UUID] = set()
    units: list[tuple[DocumentChunk, int | None]] = []
    mentions: dict[UUID, int] = {}
    members_of: dict[UUID, tuple[UUID, ...]] = {}

    for scene in scenes:
        members = [by_id[cid] for cid in scene.chunk_ids if cid in by_id]
        text = "\n\n".join(c.text for c, _ in members if c.text.strip())
        if not members or not text:
            continue
        covered.update(c.id for c, _ in members)
        lead, lead_chapter = members[0]
        unit = DocumentChunk(
            id=lead.id,
            book_id=lead.book_id,
            chapter_id=lead.chapter_id,
            text=text,
            pages=sorted({p for c, _ in members for p in c.pages}),
            page_start=min(c.page_start for c, _ in members),
            page_end=max(c.page_end for c, _ in members),
        )
        units.append((unit, lead_chapter))
        mentions[lead.id] = len(scene.participants)
        members_of[lead.id] = tuple(c.id for c, _ in members)

    for chunk, chapter in chunks:
        if chunk.id in covered:
            continue
        units.append((chunk, chapter))
        mentions[chunk.id] = -1
        members_of[chunk.id] = (chunk.id,)

    units.sort(key=lambda pair: (pair[0].page_start, str(pair[0].id)))

    return units, mentions, members_of
