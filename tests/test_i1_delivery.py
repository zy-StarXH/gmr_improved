from __future__ import annotations

from gmr_improved.i0_delivery import file_record, verify_file_records


def test_delivery_record_detects_tampering(tmp_path) -> None:
    path = tmp_path / "artifact.txt"
    path.write_text("original", encoding="utf-8")
    record = file_record(tmp_path, "artifact.txt")
    assert verify_file_records(tmp_path, [record]) == []
    path.write_text("tampered", encoding="utf-8")
    assert verify_file_records(tmp_path, [record]) == ["sha256:artifact.txt"]
