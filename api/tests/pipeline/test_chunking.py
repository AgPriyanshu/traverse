from pathlib import Path

import pytest

from api.config.settings import Settings
from api.contracts.enums import DetectionMethod
from api.contracts.pipeline import ChunkPayload
from api.pipeline.chunking import (
    DocumentChunker,
    _normalize_chapter_number,
    _plan_heading_batches,
    _roman_to_int,
    resolve_device,
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
    def test_parses_a_chapter_heading(
        self, chunker: DocumentChunker, heading: str, number: int, title: str | None
    ) -> None:
        info = chunker._parse_chapter_heading(heading)

        assert info.is_chapter
        assert info.number == number
        assert info.title == title
        assert info.detection_method is DetectionMethod.REGEX

    @pytest.mark.parametrize("heading", ["Contents", "About the Author", "Prologue"])
    def test_rejects_a_non_chapter_when_the_llm_is_off(
        self, chunker: DocumentChunker, heading: str
    ) -> None:
        info = chunker._parse_chapter_heading(heading)

        assert not info.is_chapter

    def test_collapses_whitespace_into_the_heading_text(
        self, chunker: DocumentChunker
    ) -> None:
        info = chunker._parse_chapter_heading("  Chapter\n 2 \t Onward  ")

        assert info.text == "Chapter 2 Onward"


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


class TestHeadingBatching:
    """The stopgap batcher ahead of be2's ``api.llm.plan_batches`` (S2.7)."""

    def test_an_empty_input_needs_no_calls(self) -> None:
        assert _plan_heading_batches([], max_context=1000, output_reserve=100) == []

    def test_short_headings_fit_in_one_batch(self) -> None:
        headings = [f"Chapter {n}" for n in range(1, 21)]

        batches = _plan_heading_batches(headings, max_context=4000, output_reserve=500)

        assert len(batches) == 1
        assert batches[0].items == headings

    def test_a_tight_budget_splits_into_several_calls(self) -> None:
        headings = [f"Chapter {n}: A Very Long Chapter Title Indeed" for n in range(20)]

        batches = _plan_heading_batches(headings, max_context=200, output_reserve=50)

        assert len(batches) > 1
        # Every heading is covered exactly once, in order, none dropped.
        assert [h for batch in batches for h in batch.items] == headings

    def test_a_single_heading_is_never_split(self) -> None:
        batches = _plan_heading_batches(
            ["Chapter One"], max_context=50, output_reserve=45
        )

        assert len(batches) == 1
        assert batches[0].items == ["Chapter One"]
        assert batches[0].was_split is False


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
