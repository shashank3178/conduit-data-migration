from types import SimpleNamespace

from app.services.execution_scheduler import resource_aware_table_order, retry_delay


def test_resource_aware_order_prioritizes_larger_unfinished_tables():
    small = SimpleNamespace(id="small", source_schema="public", source_table="small")
    large = SimpleNamespace(id="large", source_schema="public", source_table="large")
    done = SimpleNamespace(id="done", source_schema="public", source_table="done")
    progress = {
        "small": SimpleNamespace(total_rows=10, status="queued"),
        "large": SimpleNamespace(total_rows=1000, status="queued"),
        "done": SimpleNamespace(total_rows=5000, status="completed"),
    }

    assert resource_aware_table_order([small, done, large], progress) == [
        large, small, done
    ]


def test_retry_delay_is_exponential_and_capped():
    assert retry_delay(0) == 0.5
    assert retry_delay(1) == 1.0
    assert retry_delay(2) == 2.0
    assert retry_delay(10) == 8.0
