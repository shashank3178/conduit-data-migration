import pytest

from app.services.postgres_copy_engine import _adapt_row


def test_copy_adapts_json_and_jsonb_values():
    from psycopg.types.json import Json, Jsonb

    adapted = _adapt_row(
        [{"name": "Ada"}, ["x", "y"], 7],
        ["document", "tags", "id"],
        {"document": "json", "tags": "jsonb", "id": "bigint"},
    )
    assert isinstance(adapted[0], Json)
    assert isinstance(adapted[1], Jsonb)
    assert adapted[0].obj == {"name": "Ada"}
    assert adapted[1].obj == ["x", "y"]
    assert adapted[2] == 7


def test_copy_rejects_unmapped_python_dictionary():
    with pytest.raises(TypeError, match="destination column"):
        _adapt_row([{"unexpected": True}], ["payload"], {"payload": "text"})


def test_copy_rejects_row_width_mismatch():
    with pytest.raises(ValueError, match="values for"):
        _adapt_row([1, 2], ["id"], {"id": "integer"})



def test_write_batch_dispatches_copy_from_persisted_engine(monkeypatch):
    from types import SimpleNamespace

    from app.services import migration_execution

    expected = (2, 1, 0)
    calls = []

    def fake_copy(*args):
        calls.append(args)
        return expected

    monkeypatch.setattr(migration_execution, "copy_stage_and_merge", fake_copy)
    table = SimpleNamespace(
        destination_schema="public",
        destination_table="target",
    )
    result = migration_execution._write_batch(
        destination=object(),
        table=table,
        destination_columns=["id"],
        conflict_columns=["id"],
        rows=[(1,), (2,), (3,)],
        strategy="UPSERT",
        destination_column_types={"id": "integer"},
        write_engine="COPY",
    )

    assert result == expected
    assert len(calls) == 1
    assert calls[0][1] is table
