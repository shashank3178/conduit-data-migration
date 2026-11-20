from app.services.migration_metrics_service import batch_identity, logical_payload_bytes


def test_logical_payload_bytes_uses_utf8_json_size():
    assert logical_payload_bytes([("id", 1), ("name", "é")]) > logical_payload_bytes([("id", 1)])


def test_batch_identity_is_stable_for_same_checkpoint():
    first = batch_identity("table-id", [1], [10])
    second = batch_identity("table-id", [1], [10])
    assert first == second
    assert first != batch_identity("table-id", [1], [11])
