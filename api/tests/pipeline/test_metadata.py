from pathlib import Path

from api.pipeline.metadata import extract_title_author

from ._pdf_helpers import minimal_pdf_with_metadata

FIXTURE = Path(__file__).parent.parent / "fixtures" / "three_page_novel.pdf"


class TestExtractTitleAuthor:
    def test_reads_title_and_author_from_the_pdf(self, tmp_path: Path) -> None:
        pdf = tmp_path / "book.pdf"
        pdf.write_bytes(minimal_pdf_with_metadata("Emma", "Jane Austen"))

        title, author = extract_title_author(pdf, fallback_filename="whatever.pdf")

        assert title == "Emma"
        assert author == "Jane Austen"

    def test_falls_back_to_the_filename_when_the_pdf_has_no_title(self) -> None:
        title, author = extract_title_author(
            FIXTURE, fallback_filename="pride_and-prejudice.pdf"
        )

        assert title == "Pride And Prejudice"
        assert author is None

    def test_an_unreadable_file_still_falls_back_to_the_filename(
        self, tmp_path: Path
    ) -> None:
        garbage = tmp_path / "not_a_pdf.pdf"
        garbage.write_bytes(b"not a pdf at all")

        title, author = extract_title_author(garbage, fallback_filename="my_notes.pdf")

        assert title == "My Notes"
        assert author is None

    def test_a_filename_with_no_usable_words_is_untitled(self, tmp_path: Path) -> None:
        garbage = tmp_path / "___.pdf"
        garbage.write_bytes(b"not a pdf")

        title, _author = extract_title_author(garbage, fallback_filename="___.pdf")

        assert title == "Untitled"
