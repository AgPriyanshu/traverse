import uuid

from api.contracts.enums import StageName
from api.tasks import STAGES, ingestion_chain
from api.workers import app as worker_app
from api.workers.errors import PermanentError, TransientError
from api.workers.policy import RETRY_POLICY


class TestTaskRegistration:
    """DO1's celery-worker healthcheck asserts on exactly this."""

    def test_every_pipeline_stage_is_registered(self) -> None:
        worker_app.import_task_modules()
        registered = set(worker_app.celery_app.tasks.keys())
        owned = [name for name in StageName if name.value.startswith("pipeline.")]

        assert owned, "the frozen registry has no pipeline stages"
        for name in owned:
            assert name.value in registered

    def test_the_only_missing_stages_belong_to_another_agent(self) -> None:
        missing = worker_app.missing_stage_tasks()

        assert all(
            name.value.startswith(("relations.", "graph.")) for name in missing
        ), f"a pipeline.* stage is unregistered: {missing}"

    def test_a_task_module_that_does_not_exist_yet_does_not_break_the_worker(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            worker_app, "TASK_MODULES", ("api.pipeline.tasks", "api.nope.tasks")
        )

        assert worker_app.import_task_modules() == ["api.pipeline.tasks"]


class TestRetryPolicy:
    def test_only_transient_failures_are_retried(self) -> None:
        assert RETRY_POLICY["autoretry_for"] == (TransientError,)

    def test_backoff_is_exponential_and_bounded(self) -> None:
        assert RETRY_POLICY["retry_backoff"] is True
        assert RETRY_POLICY["retry_backoff_max"] == 300
        assert RETRY_POLICY["max_retries"] == 4

    def test_a_permanent_failure_is_not_transient(self) -> None:
        assert not issubclass(PermanentError, TransientError)

    def test_every_pipeline_task_carries_the_policy(self) -> None:
        worker_app.import_task_modules()

        for name in StageName:
            task = worker_app.celery_app.tasks.get(name.value)

            if task is None or not name.value.startswith("pipeline."):
                continue

            assert task.autoretry_for == (TransientError,)
            assert task.max_retries == 4
            assert task.acks_late is True


class TestWorkerConfiguration:
    def test_long_tasks_are_not_lost_on_worker_death(self) -> None:
        conf = worker_app.celery_app.conf

        assert conf.task_acks_late is True
        assert conf.worker_prefetch_multiplier == 1
        assert conf.task_reject_on_worker_lost is True

    def test_started_is_tracked_so_status_can_distinguish_queued_from_running(
        self,
    ) -> None:
        assert worker_app.celery_app.conf.task_track_started is True


class TestIngestionChain:
    def test_the_chain_covers_every_stage_in_order(self) -> None:
        chain = ingestion_chain(uuid.uuid4())

        assert [task.task for task in chain.tasks] == [s.value for s in STAGES]

    def test_resuming_skips_everything_before_the_stage(self) -> None:
        chain = ingestion_chain(uuid.uuid4(), from_stage=StageName.EMBED_CHUNKS)

        assert chain.tasks[0].task == StageName.EMBED_CHUNKS.value
