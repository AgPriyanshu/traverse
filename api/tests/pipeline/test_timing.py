"""Per-query latency instrumentation (S6.9): QueryTimer -> QueryLog.latency_ms."""

import time

from api.pipeline.timing import QueryTimer


class TestQueryTimer:
    def test_a_stage_records_a_positive_duration(self) -> None:
        timer = QueryTimer()

        with timer.stage("resolve"):
            time.sleep(0.01)

        payload = timer.as_dict()

        assert payload["resolve"] >= 10
        assert "total_ms" in payload

    def test_a_stage_entered_twice_accumulates_rather_than_overwrites(self) -> None:
        timer = QueryTimer()

        with timer.stage("retrieve"):
            time.sleep(0.01)
        with timer.stage("retrieve"):
            time.sleep(0.01)

        payload = timer.as_dict()

        assert payload["retrieve"] >= 20

    def test_total_ms_is_present_without_any_stage(self) -> None:
        timer = QueryTimer()

        payload = timer.as_dict()

        assert payload == {"total_ms": payload["total_ms"]}
        assert payload["total_ms"] >= 0

    def test_ttft_is_absent_until_marked(self) -> None:
        timer = QueryTimer()

        with timer.stage("route"):
            pass

        assert "ttft_ms" not in timer.as_dict()

    def test_ttft_is_measured_from_construction_not_from_generate(self) -> None:
        timer = QueryTimer()
        time.sleep(0.01)

        with timer.stage("generate"):
            time.sleep(0.01)
            timer.mark_ttft()
            time.sleep(0.01)

        payload = timer.as_dict()

        # ttft covers the pre-generate wait plus the time to the first token,
        # not just the slice inside the generate stage before marking.
        assert payload["ttft_ms"] >= 20
        assert payload["ttft_ms"] < payload["generate"] + 15

    def test_ttft_is_idempotent(self) -> None:
        timer = QueryTimer()

        timer.mark_ttft()
        first = timer.as_dict()["ttft_ms"]
        time.sleep(0.01)
        timer.mark_ttft()
        second = timer.as_dict()["ttft_ms"]

        assert first == second

    def test_every_stage_label_from_the_plan_is_accepted(self) -> None:
        timer = QueryTimer()

        for label in (
            "route",
            "resolve",
            "graph",
            "retrieve",
            "rerank",
            "generate",
            "ground",
        ):
            with timer.stage(label):
                pass

        payload = timer.as_dict()

        for label in (
            "route",
            "resolve",
            "graph",
            "retrieve",
            "rerank",
            "generate",
            "ground",
        ):
            assert label in payload
