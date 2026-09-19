from pathlib import Path

import pytest

from api.config.settings import Settings
from api.contracts.enums import DetectionMethod, LLMPurpose
from api.contracts.pipeline import ChunkPayload
from api.pipeline import chunking
from api.pipeline.chunking import (
    DocumentChunker,
    _normalize_chapter_number,
    _roman_to_int,
    resolve_device,
)
from api.pipeline.constants import (
    ChapterBatchStructuredOutput,
    ChapterInfoStructuredOutput,
)


def cpu_settings(**overrides) -> Settings:
    return Settings(embedding_device="cpu", **overrides)


class TestRomanNumerals:
    @pytest.mark.parametrize(
        ("roman", "expected"),
        [("I", 1), ("IV", 4), ("IX", 9), ("XII", 12), ("XL", 40), ("MCMXCIV", 1994)],
    )
    def test_converts_subtractive_notation(self, roman: str, expected: int) -> None:
        assert _roman_to_int(roman) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("3", 3), ("3.1", 3), ("IV", 4), ("xii", 12), ("", None), ("Nine", None)],
    )
    def test_normalizes_matched_numbers(self, raw: str, expected: int | None) -> None:
        assert _normalize_chapter_number(raw) == expected


class TestChapterHeadings:
    @pytest.fixture
    def chunker(self) -> DocumentChunker:
        return DocumentChunker(cpu_settings(), llm_classify=False)

    @pytest.mark.parametrize(
        ("heading", "number", "title"),
        [
            ("Chapter 3", 3, None),
            ("CHAPTER XII: The Return", 12, "The Return"),
            ("Chapter  4 —  A Long Walk", 4, "A Long Walk"),
            ("chap. 7", 7, None),
        ],
    )
    async def test_parses_a_chapter_heading(
        self, chunker: DocumentChunker, heading: str, number: int, title: str | None
    ) -> None:
        info = await chunker._parse_chapter_heading(heading)

        assert info.is_chapter
        assert info.number == number
        assert info.title == title
        assert info.detection_method is DetectionMethod.REGEX

    @pytest.mark.parametrize("heading", ["Contents", "About the Author", "Prologue"])
    async def test_rejects_a_non_chapter_when_the_llm_is_off(
        self, chunker: DocumentChunker, heading: str
    ) -> None:
        info = await chunker._parse_chapter_heading(heading)

        assert not info.is_chapter

    async def test_collapses_whitespace_into_the_heading_text(
        self, chunker: DocumentChunker
    ) -> None:
        info = await chunker._parse_chapter_heading("  Chapter\n 2 \t Onward  ")

        assert info.text == "Chapter 2 Onward"


class TestHeadingClassificationCallsStructuredCall:
    """``_classify_heading_batch`` against ``api.llm.structured_call``.

    Stubbed at the same boundary as the rest of the project
    (``api/AGENTS.md``): no vLLM runs in this worktree, so the interesting
    behaviour to cover here is the call's own shape and how a mismatched or
    failing response degrades, not the model's output.
    """

    @pytest.fixture
    def chunker(self) -> DocumentChunker:
        return DocumentChunker(Settings(embedding_device="cpu"), llm_classify=True)

    async def test_classifies_an_ambiguous_heading_via_structured_call(
        self, chunker: DocumentChunker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        async def fake_structured_call(prompt, schema, *, purpose, book_id, stage):
            captured.update(
                prompt=prompt,
                schema=schema,
                purpose=purpose,
                book_id=book_id,
                stage=stage,
            )

            return ChapterBatchStructuredOutput(
                items=[
                    ChapterInfoStructuredOutput(
                        is_chapter=True, number=None, title="Prologue"
                    )
                ]
            )

        monkeypatch.setattr(chunking, "structured_call", fake_structured_call)

        results = await chunker._classify_heading_batch(["Prologue"], book_id="book-1")

        assert results[0].is_chapter
        assert results[0].title == "Prologue"
        assert captured["purpose"] is LLMPurpose.CHAPTER_CLASSIFY
        assert captured["schema"] is ChapterBatchStructuredOutput
        assert captured["book_id"] == "book-1"
        assert captured["stage"] == "segment_chapters"

    async def test_a_mismatched_item_count_discards_the_batch(
        self, chunker: DocumentChunker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_structured_call(prompt, schema, *, purpose, book_id, stage):
            return ChapterBatchStructuredOutput(items=[])

        monkeypatch.setattr(chunking, "structured_call", fake_structured_call)

        results = await chunker._classify_heading_batch(["Prologue", "Interlude"])

        assert [r.is_chapter for r in results] == [False, False]


class TestDeviceResolution:
    def test_cpu_is_returned_unchanged(self) -> None:
        assert resolve_device("cpu") == "cpu"

    def test_cuda_falls_back_when_unavailable(self, monkeypatch) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        assert resolve_device("cuda") == "cpu"

    def test_chunker_takes_its_device_from_settings(self) -> None:
        chunker = DocumentChunker(cpu_settings())

        assert chunker.device == "cpu"


class TestNoHostPaths:
    def test_artifacts_path_comes_from_settings(self, tmp_path: Path) -> None:
        cache = tmp_path / "models"
        cache.mkdir()
        chunker = DocumentChunker(cpu_settings(models_cache_dir=cache))

        assert chunker._artifacts_path() == str(cache)

    def test_a_missing_cache_is_none_not_a_broken_path(self, tmp_path: Path) -> None:
        chunker = DocumentChunker(cpu_settings(models_cache_dir=tmp_path / "absent"))

        assert chunker._artifacts_path() is None


class TestChunkPayloadContract:
    """The page-provenance invariant the DB check constraint also enforces."""

    def test_page_bounds_must_agree_with_pages(self) -> None:
        with pytest.raises(ValueError, match="disagree"):
            ChunkPayload(text="x", pages=[4, 5], page_start=4, page_end=9)

    def test_pages_may_not_be_empty(self) -> None:
        with pytest.raises(ValueError):
            ChunkPayload(text="x", pages=[], page_start=1, page_end=1)

    def test_a_valid_payload_round_trips(self) -> None:
        payload = ChunkPayload(
            text="Elizabeth turned away.",
            pages=[11, 12],
            page_start=11,
            page_end=12,
            chapter_number=2,
            token_count=5,
        )

        assert payload.pages == [11, 12]
        assert payload.text_embedding is None
