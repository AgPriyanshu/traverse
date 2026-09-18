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
    def test_every_chunk_carries_page_provenance(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = chunker.generate_chunks(novel(), embed=False)

        assert chunks
        for chunk in chunks:
            assert chunk.pages
            assert chunk.page_start >= 1
            assert chunk.page_start == min(chunk.pages)
            assert chunk.page_end == max(chunk.pages)

    def test_chunks_span_the_whole_document(self, chunker: DocumentChunker) -> None:
        chunks = chunker.generate_chunks(novel(), embed=False)
        covered = {page for chunk in chunks for page in chunk.pages}

        assert covered == {1, 2, 3}

    def test_token_counts_come_from_the_model_tokenizer(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = chunker.generate_chunks(novel(), embed=False)

        assert all(chunk.token_count and chunk.token_count > 0 for chunk in chunks)

    def test_skipping_embedding_leaves_the_vector_unset(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = chunker.generate_chunks(novel(), embed=False)

        assert all(chunk.text_embedding is None for chunk in chunks)

    def test_a_chunk_with_no_provenance_is_refused(
        self, chunker: DocumentChunker
    ) -> None:
        doc = DoclingDocument(name="orphan")
        doc.pages[1] = PageItem(page_no=1, size=Size(width=612, height=792))
        doc.add_text(label="text", text="A passage that came from nowhere.")

        # Page-exact citation is the product: a chunk that cannot be cited must
        # not reach the database, however tempting a default of 0 is.
        with pytest.raises(MissingProvenanceError):
            chunker.generate_chunks(doc, embed=False)


class TestChapterCarryForward:
    def test_headings_are_detected_as_chapters(self, chunker: DocumentChunker) -> None:
        chapters = chunker.detect_chapters(novel())

        assert [chapter.number for chapter in chapters] == [1, 2]

    def test_a_mid_chapter_chunk_inherits_the_last_chapter_seen(
        self, chunker: DocumentChunker
    ) -> None:
        chunks = chunker.generate_chunks(novel(), embed=False)
        numbers = [chunk.chapter_number for chunk in chunks]

        # Everything after the first heading belongs to a chapter; nothing
        # before it does.
        assert numbers[0] == 1
        assert all(number is not None for number in numbers[: len(numbers)])


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

    def test_the_fixture_converts_and_chunks_on_cpu(
        self, chunker: DocumentChunker
    ) -> None:
        document = _load_with_retry(chunker, FIXTURE)

        assert len(document.pages) == 3

        chunks = chunker.generate_chunks(document, embed=False)

        assert chunks
        for chunk in chunks:
            assert chunk.pages
            assert chunk.page_start >= 1

    def test_the_first_chapter_heading_is_found_by_regex(
        self, chunker: DocumentChunker
    ) -> None:
        document = _load_with_retry(chunker, FIXTURE)
        chapters = chunker.detect_chapters(document)

        assert 1 in [chapter.number for chapter in chapters]
