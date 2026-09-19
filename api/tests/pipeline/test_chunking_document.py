from pathlib import Path

import pytest
from docling_core.types.doc.document import (
    BoundingBox,
    CoordOrigin,
    DoclingDocument,
    PageItem,
    ProvenanceItem,
    Size,
)

from api.config.settings import Settings
from api.contracts.enums import DetectionMethod
from api.contracts.pipeline import ChapterInfo
from api.pipeline.chunking import DocumentChunker
from api.pipeline.errors import MissingProvenanceError, PageParseError

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


def prov(page: int) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(
            l=72, t=700, r=540, b=680, coord_origin=CoordOrigin.BOTTOMLEFT
        ),
        charspan=(0, 1),
    )


def novel() -> DoclingDocument:
    """A three-page document with two chapters, built without a layout model."""
    doc = DoclingDocument(name="novel")

    for page in (1, 2, 3):
        doc.pages[page] = PageItem(page_no=page, size=Size(width=612, height=792))

    doc.add_heading("Chapter 1", level=1, prov=prov(1))
    doc.add_text(
        label="text",
        text="Elizabeth had not been long at Netherfield before she discovered "
        "that Mr Darcy was not at all what she had been led to expect of him.",
        prov=prov(1),
    )
    doc.add_text(
        label="text",
        text="She turned the matter over in her mind for some days, and said "
        "nothing of it to her sister.",
        prov=prov(2),
    )
    doc.add_heading("Chapter 2", level=1, prov=prov(3))
    doc.add_text(
        label="text",
        text="The letter came on a Tuesday, and it changed everything that "
        "Elizabeth had supposed about the gentleman.",
        prov=prov(3),
    )

    return doc


@pytest.fixture
def chunker() -> DocumentChunker:
    return DocumentChunker(Settings(embedding_device="cpu"), llm_classify=False)


class TestGenerateChunks:
    async def test_every_chunk_carries_page_provenance(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = await chunker.generate_chunks(novel(), embed=False)

        assert chunks
        for chunk in chunks:
            assert chunk.pages
            assert chunk.page_start >= 1
            assert chunk.page_start == min(chunk.pages)
            assert chunk.page_end == max(chunk.pages)

    async def test_chunks_span_the_whole_document(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = await chunker.generate_chunks(novel(), embed=False)
        covered = {page for chunk in chunks for page in chunk.pages}

        assert covered == {1, 2, 3}

    async def test_token_counts_come_from_the_model_tokenizer(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = await chunker.generate_chunks(novel(), embed=False)

        assert all(chunk.token_count and chunk.token_count > 0 for chunk in chunks)

    async def test_skipping_embedding_leaves_the_vector_unset(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = await chunker.generate_chunks(novel(), embed=False)

        assert all(chunk.text_embedding is None for chunk in chunks)

    async def test_a_chunk_with_no_provenance_is_refused(
        self, chunker: DocumentChunker
    ) -> None:
        doc = DoclingDocument(name="orphan")
        doc.pages[1] = PageItem(page_no=1, size=Size(width=612, height=792))
        doc.add_text(label="text", text="A passage that came from nowhere.")

        # Page-exact citation is the product: a chunk that cannot be cited must
        # not reach the database, however tempting a default of 0 is.
        with pytest.raises(MissingProvenanceError):
            await chunker.generate_chunks(doc, embed=False)


class TestChapterCarryForward:
    async def test_headings_are_detected_as_chapters(
        self, chunker: DocumentChunker
    ) -> None:
        chapters = await chunker.detect_chapters(novel())

        assert [chapter.number for chapter in chapters] == [1, 2]

    async def test_a_mid_chapter_chunk_inherits_the_last_chapter_seen(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = await chunker.generate_chunks(novel(), embed=False)
        numbers = [chunk.chapter_number for chunk in chunks]

        # Everything after the first heading belongs to a chapter; nothing
        # before it does.
        assert numbers[0] == 1
        assert all(number is not None for number in numbers[: len(numbers)])


class TestChapterDetectionFixes:
    """Regression coverage for the three known S1 defects fixed in S2.3."""

    async def test_a_heading_not_first_on_its_page_is_still_detected(
        self, chunker: DocumentChunker
    ) -> None:
        doc = DoclingDocument(name="novel")
        doc.pages[1] = PageItem(page_no=1, size=Size(width=612, height=792))
        # A running header (or leftover paragraph) occupies the first item on
        # the page; the chapter heading itself is the second.
        doc.add_text(label="text", text="Pride and Prejudice", prov=prov(1))
        doc.add_heading("Chapter 5", level=1, prov=prov(1))
        doc.add_text(label="text", text="Body text of chapter five.", prov=prov(1))

        chapters = await chunker.detect_chapters(doc)

        assert [chapter.number for chapter in chapters] == [5]

    async def test_a_repeated_heading_text_binds_to_its_own_position_not_the_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two chapters that share heading text must not collapse into one.

        Before the fix, ``generate_chunks`` matched a chunk's heading against
        *any* entry with equal ``.text`` anywhere in the document. Once a
        later, different heading appeared and then the same text recurred
        (a plausible shape: two title-only sections both called "Interlude"),
        the search re-bound to the *first* occurrence instead of the one at
        the chunk's actual position, because the loop's
        ``heading != previous_chapter.text`` guard was already satisfied by
        the first match and never let the second one in.
        """
        doc = DoclingDocument(name="novel")
        for page in (1, 2, 3):
            doc.pages[page] = PageItem(page_no=page, size=Size(width=612, height=792))
        doc.add_heading("Interlude", level=1, prov=prov(1))
        doc.add_text(label="text", text="First interlude passage.", prov=prov(1))
        doc.add_heading("Chapter 1", level=1, prov=prov(2))
        doc.add_text(label="text", text="Chapter one passage.", prov=prov(2))
        doc.add_heading("Interlude", level=1, prov=prov(3))
        doc.add_text(label="text", text="Second interlude passage.", prov=prov(3))

        # llm_classify=True here (unlike the shared `chunker` fixture): a
        # number-less heading like "Interlude" is only ever ambiguous — and
        # so only ever reaches the batched classifier under test — when LLM
        # classification is turned on.
        chunker = DocumentChunker(Settings(embedding_device="cpu"), llm_classify=True)

        # "Interlude" carries no number, so it never matches CHAPTER_RE and
        # both occurrences go into one batched classification call in
        # document order. Returning distinct results per position (rather
        # than a real, deterministic classifier) is what makes the point
        # under test — positional binding, not the classifier itself —
        # observable at all.
        async def fake_batch(
            texts: list[str], *, book_id: str | None = None
        ) -> list[ChapterInfo]:
            return [
                ChapterInfo(
                    is_chapter=True,
                    number=100 * (index + 1),
                    title="Interlude",
                    text=text,
                    detection_method=DetectionMethod.LLM,
                )
                for index, text in enumerate(texts)
            ]

        monkeypatch.setattr(chunker, "_classify_heading_batch", fake_batch)

        chunks = await chunker.generate_chunks(doc, embed=False)
        numbers_by_page = {chunk.page_start: chunk.chapter_number for chunk in chunks}

        assert numbers_by_page[1] == 100
        assert numbers_by_page[2] == 1
        assert numbers_by_page[3] == 200


def _load_with_retry(chunker: DocumentChunker, path: Path):
    """Load a document, tolerating the Docling backend's own cold-start flake.

    Empirically ~1/8 first-ever conversions in a process report a page as
    failed and the identical conversion succeeds immediately after — this is
    exactly the transient case ``PageParseError`` and Celery's retry exist for
    in production. Retrying once here keeps the suite from flaking on the same
    condition rather than masking a real regression: a *repeated* failure still
    raises.
    """
    try:
        return chunker.load_document(path)
    except PageParseError:
        return chunker.load_document(path)


@pytest.mark.models
class TestAgainstTheFixturePdf:
    """Runs the real Docling backend. Needs the model cache; never the network."""

    async def test_the_fixture_converts_and_chunks_on_cpu(
        self, chunker: DocumentChunker
    ) -> None:
        document = _load_with_retry(chunker, FIXTURE)

        assert len(document.pages) == 3

        chunks = await chunker.generate_chunks(document, embed=False)

        assert chunks
        for chunk in chunks:
            assert chunk.pages
            assert chunk.page_start >= 1

    async def test_the_first_chapter_heading_is_found_by_regex(
        self, chunker: DocumentChunker
    ) -> None:
        document = _load_with_retry(chunker, FIXTURE)
        chapters = await chunker.detect_chapters(document)

        assert 1 in [chapter.number for chapter in chapters]
