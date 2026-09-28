from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.ops.ablation import get_eval_run, get_latest_eval_run, record_eval_run


def _cell(*, axis: str, label: str, book_key: str | None, config: dict, metrics: dict) -> dict:
    return {"axis": axis, "label": label, "book_key": book_key, "config": config, "metrics": metrics}


async def test_record_and_read_latest_run(session: SQLModelAsyncSession) -> None:
    cells = [
        _cell(
            axis="extraction",
            label="Two-pass, full alias cascade (recommended)",
            book_key="pride-and-prejudice",
            config={
                "axis": "extraction",
                "label": "Two-pass, full alias cascade (recommended)",
                "extraction_mode": "two_pass",
                "alias_mode": "full_cascade",
                "with_human_review": False,
            },
            metrics={"precision": 0.75, "recall": 0.65, "f1": 0.70, "sample_size": 52},
        ),
        _cell(
            axis="extraction",
            label="Single-pass, string-only aliases",
            book_key=None,
            config={
                "axis": "extraction",
                "label": "Single-pass, string-only aliases",
                "extraction_mode": "single_pass",
                "alias_mode": "string_only",
            },
            metrics={"sample_size": 0},
        ),
    ]

    written = await record_eval_run(
        session,
        corpus_version="deadbeef",
        git_sha="abc123",
        notes="test run",
        cells=cells,
    )

    latest = await get_latest_eval_run(session)

    assert latest is not None
    assert latest.id == written.id
    assert latest.corpus_version == "deadbeef"
    assert latest.git_sha == "abc123"
    assert len(latest.results) == 2

    by_label = {r.label: r for r in latest.results}
    measured = by_label["Two-pass, full alias cascade (recommended)"]
    assert measured.book_key == "pride-and-prejudice"
    assert measured.config.extraction_mode == "two_pass"
    assert measured.metrics.f1 == 0.70

    blocked = by_label["Single-pass, string-only aliases"]
    assert blocked.metrics.sample_size == 0


async def test_get_latest_returns_the_most_recent_of_several_runs(
    session: SQLModelAsyncSession,
) -> None:
    first = await record_eval_run(
        session, corpus_version="v1", git_sha="sha1", notes=None, cells=[]
    )
    second = await record_eval_run(
        session, corpus_version="v2", git_sha="sha2", notes=None, cells=[]
    )

    latest = await get_latest_eval_run(session)

    assert latest is not None
    assert latest.id == second.id
    assert latest.id != first.id


async def test_get_eval_run_by_id(session: SQLModelAsyncSession) -> None:
    written = await record_eval_run(
        session, corpus_version="v1", git_sha="sha1", notes=None, cells=[]
    )

    fetched = await get_eval_run(session, written.id)

    assert fetched is not None
    assert fetched.id == written.id


async def test_get_latest_returns_none_when_no_runs_exist(
    session: SQLModelAsyncSession,
) -> None:
    latest = await get_latest_eval_run(session)

    assert latest is None
