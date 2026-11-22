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
