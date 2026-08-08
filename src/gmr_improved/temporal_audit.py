"""Independent integrity and invariant audit for completed Temporal-GMR runs."""

from __future__ import annotations

import csv
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_file(
    path: Path, expected_hash: str, mismatches: list[dict[str, Any]], label: str
) -> None:
    if not path.is_file():
        mismatches.append({"label": label, "path": str(path), "error": "missing"})
        return
    actual = sha256_file(path)
    if actual != expected_hash:
        mismatches.append(
            {
                "label": label,
                "path": str(path),
                "error": "sha256_mismatch",
                "expected": expected_hash,
                "actual": actual,
            }
        )


def audit_temporal_run(
    generation_manifest: str | Path,
    quality_manifest: str | Path,
    comparison_manifest: str | Path,
) -> dict[str, Any]:
    generation_path = Path(generation_manifest).expanduser().resolve()
    quality_path = Path(quality_manifest).expanduser().resolve()
    comparison_path = Path(comparison_manifest).expanduser().resolve()
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    mismatches: list[dict[str, Any]] = []

    _check_file(
        Path(generation["catalog"]["path"]),
        generation["catalog"]["sha256"],
        mismatches,
        "generated_catalog",
    )
    _check_file(
        Path(generation["experiment_config"]["path"]),
        generation["experiment_config"]["sha256"],
        mismatches,
        "experiment_config",
    )
    for entry in generation["frozen_artifacts"]:
        _check_file(Path(entry["path"]), entry["sha256"], mismatches, "frozen_artifact")
    for entry in generation["implementation_sources"]:
        _check_file(Path(entry["path"]), entry["sha256"], mismatches, "implementation_source")

    frame_total = 0
    trust_bound_failures: list[dict[str, Any]] = []
    max_ratio = 0.0
    for entry in generation["inputs"]:
        _check_file(
            Path(entry["source_bvh"]), entry["source_bvh_sha256"], mismatches, "source_bvh"
        )
        _check_file(
            Path(entry["output_pkl"]), entry["output_pkl_sha256"], mismatches, "output_pkl"
        )
        diagnostic_path = Path(entry["diagnostic_csv"])
        _check_file(
            diagnostic_path, entry["diagnostic_csv_sha256"], mismatches, "diagnostic_csv"
        )
        if diagnostic_path.is_file():
            with diagnostic_path.open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) != int(entry["output_frame_count"]):
                mismatches.append(
                    {
                        "label": "diagnostic_frame_count",
                        "path": str(diagnostic_path),
                        "expected": int(entry["output_frame_count"]),
                        "actual": len(rows),
                    }
                )
            ratios = [
                float(row["max_trust_region_ratio"])
                for row in rows
                if row["max_trust_region_ratio"] not in {"", "None"}
            ]
            sequence_max = max(ratios, default=0.0)
            max_ratio = max(max_ratio, sequence_max)
            if sequence_max > 1.0 + 1e-6:
                trust_bound_failures.append(
                    {"motion_name": entry["motion_name"], "max_ratio": sequence_max}
                )
        if Path(entry["output_pkl"]).is_file():
            with Path(entry["output_pkl"]).open("rb") as stream:
                payload = pickle.load(stream)
            shapes = {
                "root_pos": (int(entry["output_frame_count"]), 3),
                "root_rot": (int(entry["output_frame_count"]), 4),
                "dof_pos": (int(entry["output_frame_count"]), 29),
            }
            for key, expected_shape in shapes.items():
                value = np.asarray(payload[key])
                if value.shape != expected_shape or not np.isfinite(value).all():
                    mismatches.append(
                        {
                            "label": f"payload_{key}",
                            "path": entry["output_pkl"],
                            "expected_shape": expected_shape,
                            "actual_shape": value.shape,
                            "finite": bool(np.isfinite(value).all()),
                        }
                    )
        frame_total += int(entry["output_frame_count"])

    quality_root = quality_path.parent
    for entry in quality["outputs"]:
        output_path = quality_root / entry["path"]
        _check_file(output_path, entry["sha256"], mismatches, "quality_output")
        if output_path.is_file() and output_path.stat().st_size != int(entry["size_bytes"]):
            mismatches.append(
                {
                    "label": "quality_output_size",
                    "path": str(output_path),
                    "expected": int(entry["size_bytes"]),
                    "actual": output_path.stat().st_size,
                }
            )

    comparison_root = comparison_path.parent
    for entry in comparison["files"]:
        output_path = comparison_root / entry["path"]
        _check_file(output_path, entry["sha256"], mismatches, "comparison_output")
        if output_path.is_file() and output_path.stat().st_size != int(entry["size_bytes"]):
            mismatches.append(
                {
                    "label": "comparison_output_size",
                    "path": str(output_path),
                    "expected": int(entry["size_bytes"]),
                    "actual": output_path.stat().st_size,
                }
            )
    _check_file(
        Path(comparison["implementation"]["path"]),
        comparison["implementation"]["sha256"],
        mismatches,
        "comparison_implementation",
    )

    expected_frames = int(generation["cohort"]["total_frames"])
    if frame_total != expected_frames:
        mismatches.append(
            {
                "label": "generation_frame_total",
                "expected": expected_frames,
                "actual": frame_total,
            }
        )
    expected_motions = int(generation["cohort"]["motion_count"])
    quality_counts = quality["counts"]
    if int(quality_counts["discovered"]) != expected_motions or int(quality_counts["failed"]) != 0:
        mismatches.append(
            {
                "label": "quality_counts",
                "expected_motions": expected_motions,
                "actual": quality_counts,
            }
        )
    if trust_bound_failures:
        mismatches.extend(
            {"label": "trust_region_bound", **failure} for failure in trust_bound_failures
        )

    return {
        "schema_version": 1,
        "ok": not mismatches,
        "generation_manifest": str(generation_path),
        "generation_manifest_sha256": sha256_file(generation_path),
        "quality_manifest": str(quality_path),
        "quality_manifest_sha256": sha256_file(quality_path),
        "comparison_manifest": str(comparison_path),
        "comparison_manifest_sha256": sha256_file(comparison_path),
        "motion_count": expected_motions,
        "frame_count": frame_total,
        "quality_output_count": len(quality["outputs"]),
        "comparison_output_count": len(comparison["files"]),
        "max_trust_region_ratio": max_ratio,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }

