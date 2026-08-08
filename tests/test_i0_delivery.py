import json

from gmr_improved.i0_delivery import file_record, verify_file_records


def test_delivery_record_detects_hash_change(tmp_path):
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"ok": True}), encoding="utf-8")
    record = file_record(tmp_path, "artifact.json")
    assert verify_file_records(tmp_path, [record]) == []
    artifact.write_text(json.dumps({"ok": False}), encoding="utf-8")
    mismatches = verify_file_records(tmp_path, [record])
    assert "sha256:artifact.json" in mismatches
