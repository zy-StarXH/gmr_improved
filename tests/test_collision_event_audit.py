from __future__ import annotations

import csv
import json

from gmr_improved.collision_event_audit import _audited_body_pairs, _read_events


def test_event_audit_separates_pair_coverage_and_frame_overlap(tmp_path) -> None:
    pairs = tmp_path / "pairs.csv"
    with pairs.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["body_a_name", "body_b_name"])
        writer.writeheader()
        writer.writerow({"body_a_name": "a", "body_b_name": "b"})
    events = tmp_path / "events.csv"
    with events.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["motion_name", "event_type", "start_frame", "end_frame", "entities"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "motion_name": "m",
                "event_type": "SELF_COLLISION_NONHAND",
                "start_frame": 1,
                "end_frame": 2,
                "entities": json.dumps(["b", "a"]),
            }
        )
        writer.writerow(
            {
                "motion_name": "m",
                "event_type": "SELF_COLLISION_NONHAND",
                "start_frame": 2,
                "end_frame": 3,
                "entities": json.dumps(["c", "d"]),
            }
        )
    audited = _audited_body_pairs(pairs)
    summary, counts = _read_events(events, audited)
    assert audited == {("a", "b")}
    assert summary["event_count"] == {"audited": 1, "not_audited": 1, "total": 2}
    assert summary["unique_motion_frame_count"] == {
        "audited": 2,
        "not_audited": 2,
        "overlap": 1,
        "any": 3,
    }
    assert counts[("a", "b")] == 1
