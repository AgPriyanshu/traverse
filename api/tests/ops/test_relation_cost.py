from api.ops.graph_rebuild import _digest
from api.ops.relation_cost import cache_alert
from api.ops.vllm_metrics import (
    VllmCacheCounters,
    _first_present,
    hit_rate_between,
)


def test_cache_alert_only_fires_on_a_measured_low_rate():
    assert cache_alert(0.5)
    assert not cache_alert(0.8)
    assert not cache_alert(None)


def test_v1_engine_metric_names_are_read():
    totals = {"vllm:prefix_cache_hits_total": 3.0}

    assert (
        _first_present(
            totals, ("vllm:gpu_prefix_cache_hits_total", "vllm:prefix_cache_hits_total")
        )
        == 3.0
    )


def test_hit_rate_is_a_window_not_a_lifetime_average():
    before = VllmCacheCounters(hits=100, queries=1000)
    after = VllmCacheCounters(hits=190, queries=1100)

    assert hit_rate_between(before, after) == 0.9
    assert hit_rate_between(after, after) is None


def test_checksum_ignores_row_and_list_order():
    a = [{"id": 1, "pages": ["2:5", "1:3"]}, {"id": 2, "pages": []}]
    b = [{"id": 2, "pages": []}, {"id": 1, "pages": ["1:3", "2:5"]}]

    assert _digest(a) == _digest(b)
    assert _digest(a) != _digest([{"id": 1, "pages": ["1:3"]}, {"id": 2, "pages": []}])
