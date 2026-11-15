from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.migration_ddl import build_ddl, normalize_pg_type, quote_identifier, types_compatible


def test_postgres_type_normalization_and_compatibility():
    assert normalize_pg_type("int4") == "INTEGER"
    assert normalize_pg_type("character varying(40)") == "VARCHAR(40)"
    assert normalize_pg_type("NUMERIC(12, 2)") == "NUMERIC(12, 2)"
    assert normalize_pg_type("INTEGER; DROP TABLE users") is None
    assert types_compatible("SMALLINT", "BIGINT")
    assert not types_compatible("BIGINT", "SMALLINT")


def test_identifier_quoting_escapes_quotes():
    assert quote_identifier('customer"name') == '"customer""name"'


def test_ddl_preview_generates_schema_table_and_primary_key():
    table = SimpleNamespace(
        id="table-1",
        selected=True,
        destination_exists=False,
        source_schema="public",
        source_table="customers",
        source_table_type="table",
        destination_schema="public",
        destination_table="customers_copy",
        source_columns=[
            {"name": "id", "type": "INTEGER", "nullable": False},
            {"name": "email", "type": "VARCHAR(120)", "nullable": False},
        ],
        source_primary_key={"constrained_columns": ["id"]},
    )
    mappings = {
        "table-1": [
            SimpleNamespace(source_column="id", destination_column="id", destination_type="INTEGER", source_type="INTEGER", included=True),
            SimpleNamespace(source_column="email", destination_column="email", destination_type="VARCHAR(120)", source_type="VARCHAR(120)", included=True),
        ]
    }
    statements, warnings, count, schemas = build_ddl([table], mappings, True)
    assert statements[0] == 'CREATE SCHEMA IF NOT EXISTS "public";'
    assert 'CREATE TABLE IF NOT EXISTS "public"."customers_copy"' in statements[1]
    assert 'PRIMARY KEY ("id")' in statements[1]
    assert count == 1
    assert schemas == ["public"]


def test_ddl_rejects_unsafe_types():
    table = SimpleNamespace(
        id="table-1", selected=True, destination_exists=False,
        source_schema="public", source_table="t", source_table_type="table",
        destination_schema="public", destination_table="t_copy",
        source_columns=[{"name": "x", "type": "TEXT", "nullable": True}],
        source_primary_key={},
    )
    mappings = {"table-1": [SimpleNamespace(source_column="x", destination_column="x", destination_type="TEXT; DROP TABLE t", source_type="TEXT", included=True)]}
    with pytest.raises(HTTPException):
        build_ddl([table], mappings, False)
