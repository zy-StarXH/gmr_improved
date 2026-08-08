"""Independent integrity audit for the complete A0/A1 held-out pipeline."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(
    path: Path,
    expected_hash: str,
    mismatches: list[dict[str, Any]],
    label: str,
    expected_size: int | None = None,
) -> None:
    if not path.is_file():
        mismatches.append({"label": label, "path": str(path), "error": "missing"})
        return
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        mismatches.append(
            {
                "label": label,
                "path": str(path),
                "error": "sha256_mismatch",
                "expected": expected_hash,
                "actual": actual_hash,
            }
        )
    if expected_size is not None and path.stat().st_size != expected_size:
        mismatches.append(
            {
                "label": f"{label}_size",
                "path": str(path),
                "expected": expected_size,
                "actual": path.stat().st_size,
            }
        )


def audit_heldout(
    a0_generation_manifest: str | Path,
    a1_generation_manifest: str | Path,
    a0_quality_manifest: str | Path,
    a1_quality_manifest: str | Path,
    comparison_manifest: str | Path,
) -> dict[str, Any]:
    paths = {
        "a0_generation": Path(a0_generation_manifest).expanduser().resolve(),
        "a1_generation": Path(a1_generation_manifest).expanduser().resolve(),
        "a0_quality": Path(a0_quality_manifest).expanduser().resolve(),
        "a1_quality": Path(a1_quality_manifest).expanduser().resolve(),
        "comparison": Path(comparison_manifest).expanduser().resolve(),
    }
    manifests = {
        name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()
    }
    mismatches: list[dict[str, Any]] = []

    generation_summaries: dict[str, Any] = {}
    for variant in ("a0", "a1"):
        manifest = manifests[f"{variant}_generation"]
        if not manifest.get("complete") or manifest.get("variant") != variant:
            mismatches.append({"label": f"{variant}_generation_state", "actual": manifest.get("complete")})
        _check(
            Path(manifest["catalog"]["path"]),
            manifest["catalog"]["sha256"],
            mismatches,
            f"{variant}_catalog",
        )
        _check(
            Path(manifest["generator"]["runner_path"]),
            manifest["generator"]["runner_sha256"],
            mismatches,
            f"{variant}_runner",
        )
        _check(
            Path(manifest["generator"]["config_path"]),
            manifest["generator"]["config_sha256"],
            mismatches,
            f"{variant}_config",
        )
        for artifact in manifest["frozen_artifacts"]:
            _check(
                Path(artifact["path"]), artifact["sha256"], mismatches, "frozen_artifact"
            )
        frame_count = 0
        max_velocity = 0.0
        max_ratio = 0.0
        motion_names: list[str] = []
        for entry in manifest["inputs"]:
            motion_names.append(entry["motion_name"])
            _check(
                Path(entry["source_bvh"]),
                entry["source_bvh_sha256"],
                mismatches,
                f"{variant}_source_bvh",
            )
            output = Path(entry["output_pkl"])
            _check(
                output,
                entry["output_pkl_sha256"],
                mismatches,
                f"{variant}_output_pkl",
            )
            if output.is_file():
                with output.open("rb") as stream:
                    payload = pickle.load(stream)
                expected_frames = int(entry["output_frame_count"])
                shapes = {
                    "root_pos": (expected_frames, 3),
                    "root_rot": (expected_frames, 4),
                    "dof_pos": (expected_frames, 29),
                }
                for key, shape in shapes.items():
                    values = np.asarray(payload[key])
                    if values.shape != shape or not np.isfinite(values).all():
                        mismatches.append(
                            {
                                "label": f"{variant}_{key}_payload",
                                "motion_name": entry["motion_name"],
                                "shape": values.shape,
                                "finite": bool(np.isfinite(values).all()),
                            }
                        )
            frame_count += int(entry["output_frame_count"])
            if variant == "a1":
                diagnostic = entry["diagnostic"]
                _check(
                    Path(diagnostic["path"]),
                    diagnostic["sha256"],
                    mismatches,
                    "a1_diagnostic",
                )
                if int(diagnostic["frame_count"]) != int(entry["output_frame_count"]):
                    mismatches.append(
                        {"label": "a1_diagnostic_frame_count", "motion_name": entry["motion_name"]}
                    )
                max_velocity = max(
                    max_velocity, float(entry["max_observed_joint_velocity_rad_s"])
                )
                max_ratio = max(
                    max_ratio, float(entry["max_observed_trust_region_ratio"])
                )
        generation_summaries[variant] = {
            "motion_count": len(motion_names),
            "frame_count": frame_count,
            "motion_names": sorted(motion_names),
            "max_observed_joint_velocity_rad_s": max_velocity if variant == "a1" else None,
            "max_observed_trust_region_ratio": max_ratio if variant == "a1" else None,
        }
    if generation_summaries["a0"]["motion_names"] != generation_summaries["a1"]["motion_names"]:
        mismatches.append({"label": "generation_motion_pairing"})
    for variant in ("a0", "a1"):
        if generation_summaries[variant]["motion_count"] != 15 or generation_summaries[variant]["frame_count"] != 91627:
            mismatches.append(
                {"label": f"{variant}_cohort_size", "actual": generation_summaries[variant]}
            )
    if generation_summaries["a1"]["max_observed_trust_region_ratio"] > 1.0 + 1e-6:
        mismatches.append(
            {"label": "a1_trust_region_ratio", "actual": generation_summaries["a1"]["max_observed_trust_region_ratio"]}
        )

    quality_summaries: dict[str, Any] = {}
    for variant in ("a0", "a1"):
        path = paths[f"{variant}_quality"]
        manifest = manifests[f"{variant}_quality"]
        for entry in manifest["outputs"]:
            _check(
                path.parent / entry["path"],
                entry["sha256"],
                mismatches,
                f"{variant}_quality_output",
                int(entry["size_bytes"]),
            )
        counts = manifest["counts"]
        if int(counts["discovered"]) != 15 or int(counts["succeeded"]) != 15 or int(counts["failed"]) != 0:
            mismatches.append({"label": f"{variant}_quality_counts", "actual": counts})
        summary = pd.read_csv(path.parent / "quality_summary.csv")
        if len(summary) != 15 or int(summary["num_frames"].sum()) != 91627:
            mismatches.append({"label": f"{variant}_quality_summary_shape"})
        if not (summary["fidelity_status"] == "enabled_verified").all():
            mismatches.append({"label": f"{variant}_fidelity_status"})
        quality_summaries[variant] = {
            "output_count": len(manifest["outputs"]),
            "hard_fail_count": int(counts["hard_fail"]),
            "fidelity_verified_count": int(
                (summary["fidelity_status"] == "enabled_verified").sum()
            ),
        }

    comparison_path = paths["comparison"]
    comparison = manifests["comparison"]
    if not comparison.get("complete"):
        mismatches.append({"label": "comparison_complete"})
    for entry in comparison["files"]:
        _check(
            comparison_path.parent / entry["path"],
            entry["sha256"],
            mismatches,
            "comparison_output",
            int(entry["size_bytes"]),
        )
    _check(
        Path(comparison["implementation"]["path"]),
        comparison["implementation"]["sha256"],
        mismatches,
        "comparison_implementation",
    )
    result = json.loads(
        (comparison_path.parent / "comparison_summary.json").read_text(encoding="utf-8")
    )
    if int(result["motion_count"]) != 15 or int(result["frame_count"]) != 91627:
        mismatches.append({"label": "comparison_cohort_size"})
    if result["uncalibrated_quality_score_used"] is not False:
        mismatches.append({"label": "uncalibrated_score_usage"})

    return {
        "schema_version": 1,
        "ok": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "generation": generation_summaries,
        "quality": quality_summaries,
        "comparison": {
            "output_count": len(comparison["files"]),
            "heldout_gate_pass": bool(result["acceptance"]["heldout_gate_pass"]),
            "new_hard_fail_motions": result["acceptance"]["new_hard_fail_motions"],
            "uncalibrated_quality_score_used": result["uncalibrated_quality_score_used"],
        },
        "manifest_inputs": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
    }

