"""Pre-output audit of source-human contact labels for Contact-GMR."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contact import ContactGMRConfig, infer_human_contact_sequence
from .temporal_experiment import _read_catalog, _source_fps, sha256_file


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Contact input audit output must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def audit_contact_inputs(
    catalog_path: str | Path,
    output_dir: str | Path,
    config: ContactGMRConfig | None = None,
) -> Path:
    catalog = Path(catalog_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    parameters = config or ContactGMRConfig()
    rows = _read_catalog(catalog)
    from general_motion_retargeting.utils.lafan1 import load_bvh_file

    metrics: list[dict[str, Any]] = []
    total_frames = 0
    for row in rows:
        source = Path(row["source_bvh"]).expanduser().resolve()
        actual_hash = sha256_file(source)
        if actual_hash != row["source_bvh_sha256"]:
            raise ValueError(f"Source BVH hash mismatch: {source}")
        frames, _ = load_bvh_file(str(source), format="lafan1")
        fps = _source_fps(source)
        sequence = infer_human_contact_sequence(
            frames, fps, row["contact_policy"], parameters
        )
        left = np.array([item.left_contact for item in sequence.frames], dtype=bool)
        right = np.array([item.right_contact for item in sequence.frames], dtype=bool)
        left_enters = sum(item.left_transition == "enter" for item in sequence.frames)
        right_enters = sum(item.right_transition == "enter" for item in sequence.frames)
        metrics.append(
            {
                "motion_name": row["motion_name"],
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "num_frames": len(frames),
                "source_fps": fps,
                "ground_height_m": sequence.ground_height_m,
                "left_contact_frame_count": int(left.sum()),
                "right_contact_frame_count": int(right.sum()),
                "any_contact_frame_count": int((left | right).sum()),
                "double_contact_frame_count": int((left & right).sum()),
                "left_contact_frame_rate": float(left.mean()),
                "right_contact_frame_rate": float(right.mean()),
                "any_contact_frame_rate": float((left | right).mean()),
                "double_contact_frame_rate": float((left & right).mean()),
                "left_contact_event_count": int(left_enters),
                "right_contact_event_count": int(right_enters),
                "source_bvh_sha256": actual_hash,
            }
        )
        total_frames += len(frames)
    frame = pd.DataFrame(metrics)
    frame.to_csv(destination / "source_contact_metrics.csv", index=False)

    feet = frame[frame["contact_policy"] == "feet_only"]
    floor = frame[frame["contact_policy"] == "floor_motion"]
    if feet.empty or floor.empty:
        raise ValueError("Frozen catalog must contain feet_only and floor_motion strata")
    feet_any_count = int(feet["any_contact_frame_count"].sum())
    floor_any_count = int(floor["any_contact_frame_count"].sum())
    result = {
        "schema_version": 1,
        "motion_count": len(frame),
        "frame_count": total_frames,
        "parameters": parameters.as_dict(),
        "policy_audit": {
            "feet_only_motion_count": len(feet),
            "floor_motion_count": len(floor),
            "feet_only_any_contact_frame_count": feet_any_count,
            "feet_only_any_contact_frame_rate": feet_any_count
            / int(feet["num_frames"].sum()),
            "floor_motion_any_contact_frame_count": floor_any_count,
            "floor_motion_semantic_noop": floor_any_count == 0,
        },
        "ok": feet_any_count > 0 and floor_any_count == 0,
        "inputs": {
            "catalog": {"path": str(catalog), "sha256": _sha256(catalog)},
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "interpretation_boundary": (
            "This audit uses only source BVH foot positions and preregistered thresholds. "
            "It is not evidence that robot contacts or Contact-GMR outputs improved."
        ),
    }
    output = destination / "contact_input_audit.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "complete": True,
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
