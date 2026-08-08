"""Audit quality-evaluator collision events against the frozen body-pair set."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


EVENT_TYPE = "SELF_COLLISION_NONHAND"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Audit output directory must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _audited_body_pairs(path: Path) -> set[tuple[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"body_a_name", "body_b_name"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Collision pair CSV has no body-name columns")
    return {
        tuple(sorted((row["body_a_name"], row["body_b_name"]))) for row in rows
    }


def _read_events(
    path: Path, audited_pairs: set[tuple[str, str]]
) -> tuple[dict[str, Any], Counter[tuple[str, str]]]:
    frame_sets: dict[str, dict[str, set[int]]] = {
        "audited": defaultdict(set),
        "not_audited": defaultdict(set),
    }
    counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    frame_instances: Counter[str] = Counter()
    frame = pd.read_csv(path)
    required = {"motion_name", "event_type", "start_frame", "end_frame", "entities"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Quality event table is missing columns: {missing}")
    events = frame[frame["event_type"] == EVENT_TYPE]
    for row in events.itertuples(index=False):
        entities = json.loads(row.entities)
        if not isinstance(entities, list) or len(entities) != 2 or not all(
            isinstance(value, str) for value in entities
        ):
            raise ValueError(f"Invalid event entities for {row.motion_name}: {entities}")
        pair = tuple(sorted(entities))
        coverage = "audited" if pair in audited_pairs else "not_audited"
        start = int(row.start_frame)
        end = int(row.end_frame)
        if start < 0 or end < start:
            raise ValueError(f"Invalid event frame interval: {start}..{end}")
        counts[coverage] += 1
        pair_counts[pair] += 1
        frame_instances[coverage] += end - start + 1
        frame_sets[coverage][row.motion_name].update(range(start, end + 1))

    group_unique = {
        coverage: sum(len(values) for values in motions.values())
        for coverage, motions in frame_sets.items()
    }
    all_motions = set(frame_sets["audited"]) | set(frame_sets["not_audited"])
    any_unique = 0
    overlap_unique = 0
    for motion in all_motions:
        audited = frame_sets["audited"].get(motion, set())
        not_audited = frame_sets["not_audited"].get(motion, set())
        any_unique += len(audited | not_audited)
        overlap_unique += len(audited & not_audited)
    return (
        {
            "event_count": {
                "audited": int(counts["audited"]),
                "not_audited": int(counts["not_audited"]),
                "total": int(sum(counts.values())),
            },
            "event_frame_instance_count": {
                "audited": int(frame_instances["audited"]),
                "not_audited": int(frame_instances["not_audited"]),
                "total": int(sum(frame_instances.values())),
            },
            "unique_motion_frame_count": {
                "audited": int(group_unique["audited"]),
                "not_audited": int(group_unique["not_audited"]),
                "overlap": int(overlap_unique),
                "any": int(any_unique),
            },
            "unique_body_pair_count": int(len(pair_counts)),
        },
        pair_counts,
    )


def audit_collision_event_coverage(
    collision_pairs_csv: str | Path,
    a1_events_csv: str | Path,
    a2_events_csv: str | Path,
    output_dir: str | Path,
) -> Path:
    pair_path = Path(collision_pairs_csv).expanduser().resolve()
    a1_path = Path(a1_events_csv).expanduser().resolve()
    a2_path = Path(a2_events_csv).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    pairs = _audited_body_pairs(pair_path)
    a1, a1_pairs = _read_events(a1_path, pairs)
    a2, a2_pairs = _read_events(a2_path, pairs)

    pair_rows = []
    for pair in sorted(set(a1_pairs) | set(a2_pairs)):
        pair_rows.append(
            {
                "body_a": pair[0],
                "body_b": pair[1],
                "covered_by_audited_pair_set": pair in pairs,
                "a1_event_count": int(a1_pairs[pair]),
                "a2_event_count": int(a2_pairs[pair]),
                "delta_event_count": int(a2_pairs[pair] - a1_pairs[pair]),
            }
        )
    pd.DataFrame(pair_rows).to_csv(destination / "pair_event_counts.csv", index=False)

    result = {
        "schema_version": 1,
        "event_type": EVENT_TYPE,
        "audited_body_pair_count": len(pairs),
        "a1": a1,
        "a2": a2,
        "delta": {
            section: {
                key: a2[section][key] - a1[section][key]
                for key in a1[section]
            }
            for section in (
                "event_count",
                "event_frame_instance_count",
                "unique_motion_frame_count",
            )
        },
        "interpretation_boundary": (
            "Coverage is defined at body-pair level: at least one frozen geom pair "
            "exists for the event body pair. Unique-frame counts within coverage groups "
            "can overlap when two body pairs contact in the same motion frame."
        ),
        "inputs": {
            "collision_pairs_csv": {"path": str(pair_path), "sha256": _sha256(pair_path)},
            "a1_events_csv": {"path": str(a1_path), "sha256": _sha256(a1_path)},
            "a2_events_csv": {"path": str(a2_path), "sha256": _sha256(a2_path)},
        },
    }
    output = destination / "event_coverage_audit.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "complete": True,
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "files": [
            {"path": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in sorted(destination.iterdir())
            if path.name != "audit_manifest.json"
        ],
    }
    (destination / "audit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
