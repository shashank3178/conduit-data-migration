from datetime import datetime, timezone
import uuid

from sqlalchemy import Integer, text

from app.services.discovery_service import _plain


def test_plain_converts_sqlalchemy_type_and_expression():
    assert _plain(Integer()) == "INTEGER"
    assert _plain(text("now()")) == "now()"


def test_plain_converts_nested_metadata_values():
    value = {"id": uuid.UUID(int=1), "created": datetime(2026, 1, 1, tzinfo=timezone.utc), "items": (1, 2)}
    assert _plain(value) == {"id": str(uuid.UUID(int=1)), "created": "2026-01-01T00:00:00+00:00", "items": [1, 2]}
