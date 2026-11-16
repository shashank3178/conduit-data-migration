import os
from types import SimpleNamespace

import psycopg
import pytest

from app.services.migration_execution import _validate_table, _write_batch

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def pg_connection():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured.")
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        yield connection


def test_postgres_insert_only_and_upsert_accounting(pg_connection):
    pg_connection.execute("CREATE TEMP TABLE phase6_write_test (id BIGINT PRIMARY KEY, amount NUMERIC(12,2) NOT NULL)")
    table = SimpleNamespace(destination_schema="pg_temp", destination_table="phase6_write_test")

    with pg_connection.transaction():
        inserted = _write_batch(
            pg_connection, table, ["id", "amount"], ["id"],
            [(1, 10), (2, 20), (1, 99)], "INSERT_ONLY",
        )
    assert inserted == (2, 0, 1)

    with pg_connection.transaction():
        upserted = _write_batch(
            pg_connection, table, ["id", "amount"], ["id"],
            [(1, 99), (2, 20), (3, 30)], "UPSERT",
        )
    assert upserted == (1, 1, 1)

    rows = pg_connection.execute(
        "SELECT id, amount FROM pg_temp.phase6_write_test ORDER BY id"
    ).fetchall()
    assert rows == [(1, 99), (2, 20), (3, 30)]


def test_postgres_composite_conflict_key_upsert(pg_connection):
    pg_connection.execute(
        "CREATE TEMP TABLE phase6_composite_test "
        "(tenant_id BIGINT NOT NULL, id BIGINT NOT NULL, value TEXT, PRIMARY KEY (tenant_id, id))"
    )
    table = SimpleNamespace(destination_schema="pg_temp", destination_table="phase6_composite_test")
    with pg_connection.transaction():
        result = _write_batch(
            pg_connection, table, ["tenant_id", "id", "value"], ["tenant_id", "id"],
            [(1, 1, "before"), (1, 2, "new")], "UPSERT",
        )
    assert result == (2, 0, 0)

    with pg_connection.transaction():
        result = _write_batch(
            pg_connection, table, ["tenant_id", "id", "value"], ["tenant_id", "id"],
            [(1, 1, "after")], "UPSERT",
        )
    assert result == (0, 1, 0)


def test_postgres_streaming_reconciliation(pg_connection):
    pg_connection.execute("CREATE TEMP TABLE phase6_source (id BIGINT PRIMARY KEY, value TEXT)")
    pg_connection.execute("CREATE TEMP TABLE phase6_destination (id BIGINT PRIMARY KEY, value TEXT)")
    pg_connection.execute("INSERT INTO pg_temp.phase6_source VALUES (1, 'a'), (2, 'b'), (4, 'd')")
    pg_connection.execute("INSERT INTO pg_temp.phase6_destination VALUES (1, 'a'), (3, 'c'), (4, 'changed')")
    table = SimpleNamespace(
        source_schema="pg_temp", source_table="phase6_source",
        destination_schema="pg_temp", destination_table="phase6_destination",
    )
    assert _validate_table(
        pg_connection, pg_connection, table, ["id", "value"], ["id", "value"],
        ["id"], ["id"], 2,
    ) == 3
