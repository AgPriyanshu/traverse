import pytest
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from api.contracts.enums import StageName, StageState
from api.db.models import Book, IngestionRun, IngestionStage
from api.pipeline import repository
from api.workers.errors import PermanentError, TransientError
from api.workers.stages import finish_run, open_run, stage


async def stage_row(
    session: SQLModelAsyncSession, book: Book, name: StageName
) -> IngestionStage:
    statement = (
        select(IngestionStage)
        .join(IngestionRun, IngestionRun.id == IngestionStage.run_id)
        .where(IngestionRun.book_id == book.id)
        .where(IngestionStage.stage == name)
    )
    row = (await session.execute(statement)).scalars().one()
    await session.refresh(row)

    return row


class TestSuccessPath:
    async def test_a_completed_stage_is_recorded_as_succeeded(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        async with stage(book.id, StageName.PARSE_AND_CHUNK) as record:
            record.rows_written = 42

        row = await stage_row(session, book, StageName.PARSE_AND_CHUNK)

        assert row.state is StageState.SUCCEEDED
        assert row.attempt == 1
        assert row.rows_written == 42
        assert row.started_at is not None
        assert row.finished_at is not None
        assert row.duration_ms is not None
        assert row.error_class is None

    async def test_token_and_cost_counters_are_persisted(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        async with stage(book.id, StageName.EXTRACT_CHARACTERS) as record:
            record.input_tokens = 1200
            record.output_tokens = 300
            record.cost_usd = 0.0042

        row = await stage_row(session, book, StageName.EXTRACT_CHARACTERS)

        assert (row.input_tokens, row.output_tokens) == (1200, 300)
        assert row.cost_usd == pytest.approx(0.0042)


class TestFailurePath:
    async def test_a_failure_is_recorded_and_re_raised(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        with pytest.raises(PermanentError, match="corrupt"):
            async with stage(book.id, StageName.PARSE_AND_CHUNK):
                raise PermanentError("corrupt pdf")

        row = await stage_row(session, book, StageName.PARSE_AND_CHUNK)

        assert row.state is StageState.FAILED
        assert row.error_class == "PermanentError"
        assert row.error_message == "corrupt pdf"
        assert "PermanentError" in (row.traceback or "")

    async def test_the_failure_row_survives_the_body_rolling_back(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        """The status row is written in its own transaction, deliberately.

        A stage that rolls its data back must still leave a readable failure
        behind, or a crashed book is indistinguishable from an unstarted one.
        """
        with pytest.raises(TransientError):
            async with stage(book.id, StageName.EMBED_CHUNKS):
                await repository.bulk_insert_chunks(session, book.id, [])
                raise TransientError("broker went away")

        row = await stage_row(session, book, StageName.EMBED_CHUNKS)

        assert row.state is StageState.FAILED


class TestRetryTransitions:
    async def test_a_retry_bumps_the_attempt_rather_than_orphaning_the_row(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        with pytest.raises(TransientError):
            async with stage(book.id, StageName.EMBED_CHUNKS):
                raise TransientError("vllm still warming")

        async with stage(book.id, StageName.EMBED_CHUNKS) as record:
            record.rows_written = 8

        row = await stage_row(session, book, StageName.EMBED_CHUNKS)

        assert row.attempt == 2
        assert row.state is StageState.SUCCEEDED
        assert row.error_class is None
        assert row.error_message is None
        assert row.traceback is None

    async def test_a_worker_killed_mid_stage_leaves_the_row_running(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        manager = stage(book.id, StageName.SEGMENT_CHAPTERS)
        await manager.__aenter__()

        # No __aexit__: this is what SIGKILL looks like from the database's side.
        row = await stage_row(session, book, StageName.SEGMENT_CHAPTERS)

        assert row.state is StageState.RUNNING
        assert row.finished_at is None

        async with stage(book.id, StageName.SEGMENT_CHAPTERS):
            pass

        await session.refresh(row)

        assert row.attempt == 2
        assert row.state is StageState.SUCCEEDED

    async def test_every_attempt_of_a_book_shares_one_run(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        async with stage(book.id, StageName.PARSE_AND_CHUNK):
            pass
        async with stage(book.id, StageName.SEGMENT_CHAPTERS):
            pass

        runs = (
            (
                await session.execute(
                    select(IngestionRun).where(IngestionRun.book_id == book.id)
                )
            )
            .scalars()
            .all()
        )

        assert len(runs) == 1

    async def test_a_closed_run_starts_a_fresh_one(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        run = await open_run(session, book.id)
        await session.commit()
        await finish_run(session, run.id)
        await session.commit()

        async with stage(book.id, StageName.PARSE_AND_CHUNK):
            pass

        runs = (
            (
                await session.execute(
                    select(IngestionRun).where(IngestionRun.book_id == book.id)
                )
            )
            .scalars()
            .all()
        )

        assert len(runs) == 2


class TestStatusReadback:
    async def test_stages_come_back_in_pipeline_order(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        async with stage(book.id, StageName.EMBED_CHUNKS):
            pass
        async with stage(book.id, StageName.PARSE_AND_CHUNK):
            pass

        statuses = await repository.get_stage_statuses(session, book.id)

        assert [status.stage for status in statuses] == [
            StageName.PARSE_AND_CHUNK,
            StageName.EMBED_CHUNKS,
        ]

    async def test_a_failure_message_reaches_the_status_contract(
        self, session: SQLModelAsyncSession, book: Book
    ) -> None:
        with pytest.raises(PermanentError):
            async with stage(book.id, StageName.PARSE_AND_CHUNK):
                raise PermanentError("cannot convert novel.pdf")

        statuses = await repository.get_stage_statuses(session, book.id)

        assert statuses[0].state is StageState.FAILED
        assert statuses[0].error == "cannot convert novel.pdf"
