import os
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/metadata")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.local")
os.environ.setdefault("AUTH0_ISSUER", "https://example.auth0.com/")

from app.services import migration_execution as execution
from app.services.migration_execution import (
    _get_destination_column_types,
    _json_key,
    _restore_key,
    _validate_table,
    _validate_table_detailed,
    _write_batch,
    _write_with_isolation,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        return FakeResult(self.rows)


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        assert not self.connection.in_transaction
        self.connection.in_transaction = True
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        self.connection.in_transaction = False
        if exc_type is None:
            self.connection.committed_transactions += 1
        else:
            self.connection.rolled_back_transactions += 1
        return False


class FakeMetadataConnection:
    def __init__(self, rows):
        self.rows = rows
        self.in_transaction = False
        self.committed_transactions = 0
        self.rolled_back_transactions = 0

    def transaction(self):
        return FakeTransaction(self)

    def execute(self, query, params):
        assert self.in_transaction, "catalog query must run inside its own transaction"
        self.query = query
        self.params = params
        return FakeResult(self.rows)


def test_checkpoint_key_round_trip_for_supported_postgres_types():
    identifier = uuid4()
    values = (42, Decimal("19.95"), identifier, date(2026, 11, 17),
              datetime(2026, 11, 17, 10, 30, tzinfo=UTC), "customer-1")
    metadata = [
        {"type": "BIGINT"}, {"type": "NUMERIC(10,2)"}, {"type": "UUID"},
        {"type": "DATE"}, {"type": "TIMESTAMP WITH TIME ZONE"}, {"type": "VARCHAR(80)"},
    ]
    restored = _restore_key(_json_key(values), metadata)
    assert restored == values


def test_checkpoint_rejects_unsupported_or_null_key_types():
    try:
        _restore_key([None], [{"type": "INTEGER"}])
    except ValueError as exc:
        assert "NULL" in str(exc)
    else:
        raise AssertionError("NULL primary-key checkpoint must be rejected")

    assert _restore_key([True], [{"type": "BOOLEAN"}]) == (True,)


def test_destination_column_type_lookup_commits_its_own_transaction():
    connection = FakeMetadataConnection([("payload", "jsonb"), ("id", "integer")])
    table = SimpleNamespace(destination_schema="public", destination_table="target")

    result = _get_destination_column_types(connection, table, ["payload", "id"])

    assert result == {"payload": "jsonb", "id": "integer"}
    assert connection.committed_transactions == 1
    assert connection.rolled_back_transactions == 0
    assert connection.in_transaction is False


class FakeWriteTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeWriteConnection:
    def transaction(self):
        return FakeWriteTransaction()


def test_write_isolation_splits_failed_batches_instead_of_retrying_every_row(monkeypatch):
    import psycopg

    bad_key = (3,)
    recorded_errors = []

    def fake_write_batch(_connection, _table, _columns, _conflicts, rows, _strategy, _types, _write_engine):
        if any(row[0] == bad_key[0] for row in rows):
            raise psycopg.errors.CheckViolation("test constraint violation")
        return len(rows), 0, 0

    monkeypatch.setattr(execution, "_write_batch", fake_write_batch)
    monkeypatch.setattr(
        execution,
        "_record_row_error",
        lambda _db, _run, _progress, key, _key_columns, exc: recorded_errors.append((key, exc)),
    )

    result = _write_with_isolation(
        FakeWriteConnection(),
        object(),
        object(),
        object(),
        SimpleNamespace(destination_schema="public", destination_table="target"),
        ["id", "value"],
        {},
        ["id"],
        ["id"],
        [(1, "a"), (2, "b"), (3, "bad"), (4, "d")],
        [(1,), (2,), (3,), (4,)],
        "INSERT_ONLY",
    )

    assert result[:4] == (3, 0, 0, 1)
    assert result[4] == [bad_key]
    assert [key for key, _ in recorded_errors] == [bad_key]
    # The recursive algorithm probes batches, then isolates only the bad row;
    # it does not execute one INSERT transaction for every original row.


def test_insert_only_counts_conflicts_as_skipped():
    connection = FakeConnection([(1,), (1,)])
    table = SimpleNamespace(destination_schema="public", destination_table="target")
    result = _write_batch(connection, table, ["id", "value"], ["id"],
                          [(1, "a"), (2, "b"), (3, "c")], "INSERT_ONLY")
    assert result == (2, 0, 1)
    assert len(connection.params) == 6


def test_upsert_separates_insert_update_and_unchanged():
    connection = FakeConnection([(True,), (False,)])
    table = SimpleNamespace(destination_schema="public", destination_table="target")
    result = _write_batch(connection, table, ["id", "value"], ["id"],
                          [(1, "a"), (2, "b"), (3, "c")], "UPSERT")
    assert result == (1, 1, 1)


class FakeNamedCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query):
        return None

    def fetchmany(self, size):
        result = self.rows[self.position:self.position + size]
        self.position += len(result)
        return result


class FakeReadConnection:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def cursor(self, name):
        return FakeNamedCursor(self.rows)

    def commit(self):
        self.commits += 1


def test_streaming_reconciliation_counts_missing_extra_and_changed_rows():
    table = SimpleNamespace(
        source_schema="public", source_table="source",
        destination_schema="public", destination_table="destination",
    )
    source = FakeReadConnection([(1, "a"), (2, "b"), (4, "d")])
    destination = FakeReadConnection([(1, "a"), (3, "c"), (4, "changed")])
    mismatch = _validate_table(
        source, destination, table, ["id", "value"], ["id", "value"],
        ["id"], ["id"], 2,
    )
    assert mismatch == 3


def test_validation_returns_actionable_counts_and_closes_read_transactions():
    table = SimpleNamespace(
        source_schema="public", source_table="source",
        destination_schema="public", destination_table="destination",
    )
    source = FakeReadConnection([(1, "same"), (2, "source-only"), (3, "before")])
    destination = FakeReadConnection([(1, "same"), (3, "after"), (4, "destination-only")])

    result = _validate_table_detailed(
        source, destination, table, ["id", "value"], ["id", "value"],
        ["id"], ["id"], 2,
    )

    assert result["source_rows"] == 3
    assert result["destination_rows"] == 3
    assert result["missing_in_destination"] == 1
    assert result["extra_in_destination"] == 1
    assert result["changed_rows"] == 1
    assert result["matched_rows"] == 2
    assert result["mismatch_rows"] == 3
    assert result["exact_match_rows"] == 1
    assert result["data_consistency_percent"] == 33.3333
    assert result["validation_checks"] == {
        "row_count_match": True,
        "primary_key_set_match": False,
        "mapped_column_values_match": False,
        "all_rows_exact_match": False,
    }
    assert {sample["reason"] for sample in result["samples"]} == {
        "MISSING_IN_DESTINATION", "EXTRA_IN_DESTINATION", "COLUMN_VALUE_MISMATCH",
    }
    assert source.commits == 1
    assert destination.commits == 1


def test_timestamp_validation_uses_destination_timezone_for_naive_to_timestamptz():
    from zoneinfo import ZoneInfo

    source_value = datetime(2026, 11, 22, 12, 0, 0)
    destination_value = source_value.replace(tzinfo=ZoneInfo("UTC"))
    assert execution._timestamp_values_equal(
        source_value, destination_value,
        "timestamp without time zone", "timestamp with time zone", "UTC",
    )
    assert not execution._timestamp_values_equal(
        source_value, destination_value,
        "timestamp without time zone", "timestamp with time zone", "Asia/Kolkata",
    )


def test_timestamp_validation_compares_instants_for_timestamptz():
    from datetime import timedelta, timezone

    source_value = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
    destination_value = datetime(
        2026, 11, 22, 17, 30,
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    assert execution._timestamp_values_equal(
        source_value, destination_value,
        "timestamp with time zone", "timestamp with time zone", "UTC",
    )


def test_validation_detects_destination_rows_for_empty_source_table():
    table = SimpleNamespace(
        source_schema="public", source_table="source",
        destination_schema="public", destination_table="destination",
    )
    source = FakeReadConnection([])
    destination = FakeReadConnection([(1, "destination-only")])

    result = _validate_table_detailed(
        source, destination, table, ["id", "value"], ["id", "value"],
        ["id"], ["id"], 10,
    )

    assert result["source_rows"] == 0
    assert result["destination_rows"] == 1
    assert result["extra_in_destination"] == 1
    assert result["mismatch_rows"] == 1
    assert result["data_consistency_percent"] == 0.0
    assert result["validation_checks"]["row_count_match"] is False
    assert result["samples"][0]["reason"] == "EXTRA_IN_DESTINATION"


def test_validation_does_not_treat_boolean_true_as_integer_one():
    table = SimpleNamespace(
        source_schema="public", source_table="source",
        destination_schema="public", destination_table="destination",
    )
    source = FakeReadConnection([(1, True)])
    destination = FakeReadConnection([(1, 1)])

    result = _validate_table_detailed(
        source, destination, table, ["id", "enabled"], ["id", "enabled"],
        ["id"], ["id"], 10,
    )

    assert result["changed_rows"] == 1
    assert result["samples"][0]["reason"] == "TYPE_MISMATCH"


def test_checkpoint_restores_float_and_time_primary_keys():
    from datetime import time

    values = (12.5, time(9, 30, 15))
    metadata = [{"type": "DOUBLE PRECISION"}, {"type": "TIME"}]
    assert _restore_key(_json_key(values), metadata) == values
