import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/metadata")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.local")
os.environ.setdefault("AUTH0_ISSUER", "https://example.auth0.com/")

from app.services.migration_metrics_service import logical_payload_bytes


def test_logical_payload_estimate_avoids_json_serialization(monkeypatch):
    monkeypatch.delenv("CONDUIT_EXACT_LOGICAL_BYTES", raising=False)
    rows = [("hello", 123, b"abc", {"k": "v"})]
    assert logical_payload_bytes(rows) == 5 + 3 + 3 + 1 + 1


def test_exact_logical_payload_mode_preserves_legacy_json_measurement(monkeypatch):
    import json

    monkeypatch.setenv("CONDUIT_EXACT_LOGICAL_BYTES", "1")
    rows = [("hello", 123)]
    expected = len(json.dumps(rows[0], default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    assert logical_payload_bytes(rows) == expected
