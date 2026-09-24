"""The ``pipeline.*`` half of the ingestion chain.

Registered under the frozen names from ``StageName``; the names are the
contract and are already referenced by ``api.tasks.ingestion_chain``. Bodies
land stage by stage across Sprints 2 and 3 — the registration, the retry policy
and the status recording are what Sprint 1 owes.
"""

import asyncio
import json
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

from ..contracts.enums import StageName
from ..contracts.pipeline import ChapterInfo
from ..db.engine import db_session
from ..db.models import DocumentChunk
from ..extraction import aliases as alias_cascade
from ..extraction import characters as character_records
from ..extraction import discovery, rejection
from ..extraction import repository as extraction_repository
from ..tasks import celery_app
from ..workers.errors import PermanentError, TransientError
from ..workers.locks import book_roster_lock
from ..workers.policy import RETRY_POLICY
from ..workers.stages import StageRecord, stage
from . import repository, scene_stage
from .chunking import DocumentChunker
from .storage import StorageError, store

StageBody = Callable[[UUID, StageRecord], Awaitable[None]]

# The chapter-detection side artifact parse_and_chunk writes so segment_chapters
# never has to pay Docling's conversion cost a second time — see _parse_and_chunk.
_CHAPTERS_ARTIFACT = "books/{book_id}/chapters.json"


async def _fetch_to_temp(key: str, dest: Path, *, missing_is_permanent: bool) -> None:
    """Download an object, reclassifying storage failures for Celery's retry policy.

    Args:
        key: Object-storage key.
        dest: Local path to write to.
        missing_is_permanent: Whether a missing object means a prior stage
            never ran (unrecoverable by retrying this one) as opposed to any
            other storage failure, which is presumed transient.

    Raises:
        PermanentError: The object does not exist and ``missing_is_permanent``.
        TransientError: Any other storage failure.
    """
    if missing_is_permanent and not await store.exists(key):
        raise PermanentError(f"{key} does not exist; an earlier stage must run first")

    try:
        await store.get_object(key, dest)
    except StorageError as exc:
        raise TransientError(str(exc)) from exc


def _locked(body: StageBody) -> StageBody:
    async def run(book_id: UUID, record: StageRecord) -> None:
        async with book_roster_lock(book_id):
            await body(book_id, record)

    return run


async def _run_stage(book_id: UUID, name: StageName, body: StageBody) -> dict:
    async with stage(book_id, name) as record:
        await body(book_id, record)

    return {
        "book_id": str(book_id),
        "stage": name.value,
        "attempt": record.attempt,
        "rows_written": record.rows_written,
    }


def _execute(book_id: str, name: StageName, body: StageBody) -> dict:
    return asyncio.run(_run_stage(UUID(book_id), name, body))


async def _parse_and_chunk(book_id: UUID, record: StageRecord) -> None:
    """Fetch the source PDF, chunk it, and stash chapter detection for reuse.

    Chapter detection (``prepare_chapters``) runs here rather than being
    deferred entirely to ``segment_chapters``: it is already needed to assign
    each chunk its carried-forward chapter number, and paying Docling's
    conversion cost a second time just to detect chapters would double the
    single most expensive step in the pipeline. The result is written to
    ``_CHAPTERS_ARTIFACT`` for ``segment_chapters`` to pick up.
    """
    async with db_session() as session:
        book = await repository.get_book(session, book_id)

        if book is None or not book.storage_key:
            raise PermanentError(f"book {book_id} has no stored source file")

        storage_key = book.storage_key

    with tempfile.TemporaryDirectory() as tmp_dir:
        source_path = Path(tmp_dir) / "source.pdf"
        await _fetch_to_temp(storage_key, source_path, missing_is_permanent=True)

        chunker = DocumentChunker()
        document = chunker.load_document(source_path)
        prepared = await chunker.prepare_chapters(document, book_id=str(book_id))
        chapters = await chunker.detect_chapters(
            document, book_id=str(book_id), prepared=prepared
        )
        chunks = await chunker.generate_chunks(
            document, embed=False, book_id=str(book_id), prepared=prepared
        )
        page_count = len(document.pages)

    page_ranges = repository.page_ranges_from_payloads(chunks)
    await _store_chapters_artifact(book_id, chapters, page_ranges)

    async with db_session() as session:
        # Idempotent re-run (F1.5): a retry or an explicit reprocess replaces
        # this book's chunks rather than appending a second copy of them.
        await repository.delete_chunks(session, book_id)
        rows_written = await repository.bulk_insert_chunks(session, book_id, chunks)
        await repository.set_book_page_count(session, book_id, page_count)

    record.rows_written = rows_written


async def _store_chapters_artifact(
    book_id: UUID,
    chapters: list[ChapterInfo],
    page_ranges: dict[int | None, tuple[int, int]],
) -> None:
    """Write detected chapters and their page ranges for ``segment_chapters``.

    Page ranges travel alongside the chapters rather than being re-derived by
    the next stage: on a first ingest nothing yet links a chunk to a chapter,
    so ``repository.chapter_page_ranges`` (which joins on that link) would
    come back empty. ``page_ranges_from_payloads`` is the only source of this
    while the ``ChunkPayload``s are still in hand.
    """
    payload = {
        "chapters": [chapter.model_dump(mode="json") for chapter in chapters],
        "page_ranges": {
            "null" if number is None else str(number): list(bounds)
            for number, bounds in page_ranges.items()
        },
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        artifact_path = Path(handle.name)

    try:
        await store.put_stream(
            _CHAPTERS_ARTIFACT.format(book_id=book_id),
            artifact_path,
            content_type="application/json",
        )
    finally:
        artifact_path.unlink(missing_ok=True)


async def _segment_chapters(book_id: UUID, record: StageRecord) -> None:
    """Persist the chapters ``parse_and_chunk`` detected and link every chunk.

    Reads the side artifact rather than re-running Docling: see
    ``_parse_and_chunk``.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifact_path = Path(tmp_dir) / "chapters.json"
        await _fetch_to_temp(
            _CHAPTERS_ARTIFACT.format(book_id=book_id),
            artifact_path,
            missing_is_permanent=True,
        )
        payload = json.loads(artifact_path.read_text())

    chapters = [ChapterInfo.model_validate(item) for item in payload["chapters"]]
    page_ranges = {
        None if key == "null" else int(key): (bounds[0], bounds[1])
        for key, bounds in payload["page_ranges"].items()
    }

    async with db_session() as session:
        await repository.upsert_chapters(
            session, book_id, chapters, page_ranges=page_ranges
        )
        updated = await repository.assign_chunk_chapters(session, book_id)

    record.rows_written = updated


# BGE-M3's own context is 8192 tokens; a wide margin below that keeps one
# batch's total input comfortably inside memory on CPU (worktree) and GPU
# (integration) alike without needing a per-row cap.
_EMBED_BATCH_TOKEN_BUDGET = 8000


async def _embed_chunks(book_id: UUID, record: StageRecord) -> None:
    """Embed every chunk of a book that does not have a vector yet.

    Batched by cumulative ``token_count`` rather than row count: a handful of
    near-max-length chunks costs as much compute as many short ones, so
    sizing by row count alone under- or over-shoots memory depending on the
    prose. Each batch commits before the next one starts, so a worker killed
    mid-book leaves whatever finished actually persisted rather than
    discarding it — ``list_chunks_needing_embedding`` is what lets a restart
    resume from there instead of re-embedding the whole book (F1.2).

    Embeds each chunk's stored ``text`` rather than a heading-contextualized
    version. ``chunker.contextualize`` (used when ``parse_and_chunk`` embeds
    inline) needs the chunk's headings, which live only on the transient
    Docling ``DocChunk`` from parsing and never reach ``ChunkPayload`` — see
    SCR-4 in ``plans/sprint-2/SCR.md``. Known, documented quality gap, not a
    silent one; not blocking for this sprint.
    """
    async with db_session() as session:
        pending = await repository.list_chunks_needing_embedding(session, book_id)

    chunker = DocumentChunker()
    total_written = 0
    batch: list[DocumentChunk] = []
    batch_tokens = 0

    async def flush() -> None:
        nonlocal total_written, batch, batch_tokens

        if not batch:
            return

        vectors = chunker.embed_texts([chunk.text for chunk in batch])
        embeddings = dict(zip((chunk.id for chunk in batch), vectors, strict=True))

        async with db_session() as flush_session:
            total_written += await repository.set_chunk_embeddings(
                flush_session, embeddings
            )

        batch, batch_tokens = [], 0

    for chunk in pending:
        tokens = chunk.token_count or 0

        if batch and batch_tokens + tokens > _EMBED_BATCH_TOKEN_BUDGET:
            await flush()

        batch.append(chunk)
        batch_tokens += tokens

    await flush()

    record.rows_written = total_written


async def _extract_characters(book_id: UUID, record: StageRecord) -> None:
    """Pass 1 (S3.1): sweep every chunk, then reject non-characters (S3.2).

    Both steps run in one stage because rejection needs discovery's raw
    contexts and nothing downstream needs to see the un-rejected set — a
    partial re-run would otherwise have to reload the same chunks twice.
    """
    async with db_session() as session:
        chunks = await repository.list_chunks_with_chapter_number(session, book_id)

    mentions = await discovery.discover_mentions(chunks, book_id=book_id)
    aggregated = extraction_repository.aggregate_mentions(mentions)

    async with db_session() as session:
        await extraction_repository.replace_candidates(session, book_id, aggregated)
        candidates = await extraction_repository.list_candidates(session, book_id)

    rejections, corrected_to_person = await rejection.classify_candidates(
        candidates, book_id=book_id
    )

    async with db_session() as session:
        await extraction_repository.mark_as_person(session, corrected_to_person)
        rejected_count = await extraction_repository.reject_candidates(
            session, book_id, rejections
        )

    record.rows_written = len(aggregated) - rejected_count


async def _resolve_aliases(book_id: UUID, record: StageRecord) -> None:
    """Alias clustering (S3.3), collision splitting (S3.4), roster persistence (S3.5).

    Also builds scenes and attributes dialogue speakers (S4.8, S4.9), since the
    stage chain is frozen and both need the roster this stage persists.

    ``pipeline.reconcile_characters`` — the project-wide merge across books —
    is S5's stage, not this one's; a standalone book's project has exactly
    one book, so persisting this book's clusters as the project's roster
    directly is correct until that stage exists.
    """
    async with db_session() as session:
        book = await repository.get_book(session, book_id)

        if book is None:
            raise PermanentError(f"book {book_id} does not exist")

        project_id = book.project_id
        candidates = await extraction_repository.list_candidates(session, book_id)

    clusters = await alias_cascade.cluster_candidates(candidates, book_id=book_id)
    rows = await character_records.build_character_rows(clusters, book_id=book_id)
    mention_assignments = {
        candidate_id: cluster.cluster_key
        for cluster in clusters
        for candidate_id in cluster.candidate_ids
    }

    async with db_session() as session:
        await extraction_repository.delete_book_characters(session, book_id)
        persisted = await extraction_repository.persist_characters(
            session, book_id, project_id, rows
        )
        await extraction_repository.set_cluster_keys(session, mention_assignments)

        for cluster in clusters:
            if cluster.collision_suspected and cluster.collision_reason:
                await extraction_repository.queue_collision_review(
                    session,
                    project_id=project_id,
                    book_id=book_id,
                    name_a=cluster.canonical_name,
                    name_b=cluster.collision_partner or "",
                    reason=cluster.collision_reason,
                )

    # Scenes and speakers need the persisted roster and its mentions, and the
    # frozen stage chain has no stage of its own for them.
    async with db_session() as session:
        await scene_stage.build_scenes_and_speakers(session, book_id)

    record.rows_written = len(persisted)


async def _reconcile_characters(book_id: UUID, record: StageRecord) -> None:
    raise NotImplementedError("pipeline.reconcile_characters lands in S5.2")


@celery_app.task(name=StageName.PARSE_AND_CHUNK.value, **RETRY_POLICY)
def parse_and_chunk(book_id: str) -> dict:
    """Convert the uploaded file and write its chunks with page provenance."""
    return _execute(book_id, StageName.PARSE_AND_CHUNK, _parse_and_chunk)


@celery_app.task(name=StageName.SEGMENT_CHAPTERS.value, **RETRY_POLICY)
def segment_chapters(book_id: str) -> dict:
    """Detect chapter boundaries and attach every chunk to its chapter."""
    return _execute(book_id, StageName.SEGMENT_CHAPTERS, _segment_chapters)


@celery_app.task(name=StageName.EMBED_CHUNKS.value, **RETRY_POLICY)
def embed_chunks(book_id: str) -> dict:
    """Embed the chunks that still need it."""
    return _execute(book_id, StageName.EMBED_CHUNKS, _embed_chunks)


@celery_app.task(name=StageName.EXTRACT_CHARACTERS.value, **RETRY_POLICY)
def extract_characters(book_id: str) -> dict:
    """Pass 1 — discover candidate character mentions."""
    return _execute(book_id, StageName.EXTRACT_CHARACTERS, _locked(_extract_characters))


@celery_app.task(name=StageName.RESOLVE_ALIASES.value, **RETRY_POLICY)
def resolve_aliases(book_id: str) -> dict:
    """Cluster surface forms into one canonical character per person."""
    return _execute(book_id, StageName.RESOLVE_ALIASES, _locked(_resolve_aliases))


@celery_app.task(name=StageName.RECONCILE_CHARACTERS.value, **RETRY_POLICY)
def reconcile_characters(book_id: str) -> dict:
    """Merge this book's roster into the project-wide one."""
    return _execute(book_id, StageName.RECONCILE_CHARACTERS, _reconcile_characters)
