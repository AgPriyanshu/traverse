from uuid import uuid4

import pytest

from api.contracts.enums import StageName
from api.ops import tracing


class _Boom(Exception):
    pass


def test_run_trace_url_is_none_without_langfuse_keys() -> None:
    # The default compose profile has no `obs` secrets (docker-compose.yml
    # `obs` profile) — the test environment matches that, on purpose.
    assert tracing.run_trace_url(uuid4()) is None


def test_run_trace_id_is_stable_across_retries_of_the_same_run() -> None:
    run_id = uuid4()

    assert tracing.run_trace_id(run_id) == tracing.run_trace_id(run_id)


def test_run_trace_id_differs_across_runs() -> None:
    assert tracing.run_trace_id(uuid4()) != tracing.run_trace_id(uuid4())


def test_stage_span_is_a_working_no_op_when_disabled() -> None:
    entered = False

    with tracing.stage_span(uuid4(), uuid4(), StageName.PARSE_AND_CHUNK):
        entered = True

    assert entered


def test_stage_span_still_propagates_exceptions_when_disabled() -> None:
    span = tracing.stage_span(uuid4(), uuid4(), StageName.PARSE_AND_CHUNK)
    with pytest.raises(_Boom), span:
        raise _Boom()
