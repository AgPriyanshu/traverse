import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ingest_series import (  # noqa: E402
    BookReport,
    SeriesReport,
    render_report,
    roster_growth_lines,
)


def _report(books: list[BookReport], *, concurrent: bool = False) -> SeriesReport:
    return SeriesReport(
        series_key="anne-of-green-gables",
        project_id="proj-1",
        project_slug="anne-of-green-gables",
        concurrent=concurrent,
        books=books,
    )


def test_roster_growth_lines_flags_superlinear_cost_growth():
    books = [
        BookReport("book1", 1, pass2_cost_usd=0.10, character_count=10, status="ready"),
        BookReport("book2", 2, pass2_cost_usd=0.30, character_count=15, status="ready"),
        # roster grows 1.5x each time; cost grows 3x -- clearly superlinear.
        BookReport("book3", 3, pass2_cost_usd=0.90, character_count=22, status="ready"),
    ]

    lines = roster_growth_lines(_report(books))
    text = "\n".join(lines)

    assert "superlinear" in text.lower()


def test_roster_growth_lines_reports_linear_growth_without_alarm():
    books = [
        BookReport("book1", 1, pass2_cost_usd=0.10, character_count=10, status="ready"),
        BookReport("book2", 2, pass2_cost_usd=0.15, character_count=15, status="ready"),
        BookReport("book3", 3, pass2_cost_usd=0.22, character_count=22, status="ready"),
    ]

    lines = roster_growth_lines(_report(books))
    text = "\n".join(lines)

    assert "roughly linearly" in text


def test_roster_growth_lines_handles_missing_cost_data():
    books = [
        BookReport("book1", 1, status="ready"),
        BookReport("book2", 2, status="ready"),
    ]

    lines = roster_growth_lines(_report(books))  # must not raise.

    assert lines[0].startswith("| Book")


def test_render_report_includes_totals_and_errors():
    books = [
        BookReport("book1", 1, status="ready", wall_clock_s=12.5, pass1_cost_usd=0.01),
        BookReport("book2", 2, status="error", error="upload of book2 returned 500"),
    ]

    report = render_report(_report(books, concurrent=True))

    assert "concurrent (stress test" in report
    assert "book2: upload of book2 returned 500" in report
    assert "12.5" in report
