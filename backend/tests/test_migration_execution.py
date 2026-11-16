import os
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/metadata")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.local")
os.environ.setdefault("AUTH0_ISSUER", "https://example.auth0.com/")

from app.services.migration_execution import _json_key, _restore_key, _write_batch  # noqa: E402


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


def test_checkpoint_key_round_trip_for_supported_postgres_types():
    identifier = uuid4()
    values = (42, Decimal("19.95"), identifier, date(2026, 11, 17),
              datetime(2026, 11, 17, 10, 30, tzinfo=timezone.utc), "customer-1")
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

    try:
        _restore_key([True], [{"type": "BOOLEAN"}])
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Unsupported primary-key types must be rejected")


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
