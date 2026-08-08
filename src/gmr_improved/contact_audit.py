"""Independent integrity and intervention audit for a completed Contact-GMR run."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .temporal_audit import audit_temporal_run


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid diagnostic boolean: {value!r}")


def _as_optional_float(value: str) -> float | None:
    if value.strip() in {"", "None"}:
        return None
    return float(value)


def _record_failure(
    failures: dict[str, dict[str, Any]],
    invariant: str,
    motion_name: str,
    frame_index: int,
    detail: str,
) -> None:
    item = failures.setdefault(invariant, {"count": 0, "examples": []})
    item["count"] += 1
    if len(item["examples"]) < 5:
        item["examples"].append(
            {
                "motion_name": motion_name,
                "frame_index": frame_index,
                "detail": detail,
            }
        )


def audit_contact_run(
    generation_manifest: str | Path,
    quality_manifest: str | Path,
    comparison_manifest: str | Path,
) -> dict[str, Any]:
    """Recheck Contact-GMR file integrity and every intervention invariant."""

    generation_path = Path(generation_manifest).expanduser().resolve()
    quality_path = Path(quality_manifest).expanduser().resolve()
    comparison_path = Path(comparison_manifest).expanduser().resolve()
    base = audit_temporal_run(generation_path, quality_path, comparison_path)
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    contact_config = generation["intervention"]["contact_gmr"]
    tolerance = 1e-9
    failures: dict[str, dict[str, Any]] = {}
    policy_stats: dict[str, dict[str, Any]] = {
        "feet_only": {
            "motion_count": 0,
            "frame_count": 0,
            "human_contact_frame_count": 0,
            "anchor_active_frame_count": 0,
            "root_correction_frame_count": 0,
            "root_lift_clipped_frame_count": 0,
            "max_applied_root_lift_m": 0.0,
            "max_pre_ground_penetration_m": 0.0,
            "max_post_ground_penetration_m": 0.0,
            "max_left_anchor_error_m": 0.0,
            "max_right_anchor_error_m": 0.0,
        },
        "floor_motion": {
            "motion_count": 0,
            "frame_count": 0,
            "human_contact_frame_count": 0,
            "anchor_active_frame_count": 0,
            "root_correction_frame_count": 0,
            "root_lift_clipped_frame_count": 0,
            "max_applied_root_lift_m": 0.0,
            "max_pre_ground_penetration_m": 0.0,
            "max_post_ground_penetration_m": 0.0,
            "max_left_anchor_error_m": 0.0,
            "max_right_anchor_error_m": 0.0,
        },
    }
    manifest_aggregate_failures: list[dict[str, Any]] = []

    for entry in generation["inputs"]:
        motion_name = entry["motion_name"]
        policy = entry["contact_policy"]
        stats = policy_stats[policy]
        stats["motion_count"] += 1
        diagnostic_path = Path(entry["diagnostic_csv"])
        with diagnostic_path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        stats["frame_count"] += len(rows)
        previous_lift = 0.0
        sequence_contact_frames = 0
        sequence_anchor_frames = 0
        sequence_correction_frames = 0
        sequence_max_lift = 0.0
        sequence_max_pre = 0.0
        sequence_max_post = 0.0

        for expected_index, row in enumerate(rows):
            try:
                frame_index = int(row["frame_index"])
                if frame_index != expected_index:
                    _record_failure(
                        failures,
                        "contiguous_frame_index",
                        motion_name,
                        expected_index,
                        f"actual={frame_index}",
                    )
                if row["contact_contact_policy"] != policy:
                    _record_failure(
                        failures,
                        "contact_policy_matches_catalog",
                        motion_name,
                        frame_index,
                        f"diagnostic={row['contact_contact_policy']}, catalog={policy}",
                    )
                left = _as_bool(row["source_left_contact"])
                right = _as_bool(row["source_right_contact"])
                contact_left = _as_bool(row["contact_left_human_contact"])
                contact_right = _as_bool(row["contact_right_human_contact"])
                if (left, right) != (contact_left, contact_right):
                    _record_failure(
                        failures,
                        "source_and_runtime_contact_match",
                        motion_name,
                        frame_index,
                        f"source={(left, right)}, runtime={(contact_left, contact_right)}",
                    )
                if (
                    row["source_left_transition"] != row["contact_left_transition"]
                    or row["source_right_transition"] != row["contact_right_transition"]
                ):
                    _record_failure(
                        failures,
                        "source_and_runtime_transition_match",
                        motion_name,
                        frame_index,
                        "transition mismatch",
                    )
                active_anchor_count = int(row["contact_active_anchor_count"])
                expected_anchor_count = 0 if frame_index == 0 else int(left) + int(right)
                if policy == "floor_motion":
                    expected_anchor_count = 0
                if active_anchor_count != expected_anchor_count:
                    _record_failure(
                        failures,
                        "active_anchor_count_matches_contact",
                        motion_name,
                        frame_index,
                        f"actual={active_anchor_count}, expected={expected_anchor_count}",
                    )
                left_error = _as_optional_float(row["contact_left_anchor_error_m"])
                right_error = _as_optional_float(row["contact_right_anchor_error_m"])
                for side, state, error in (
                    ("left", left, left_error),
                    ("right", right, right_error),
                ):
                    if (error is None) == state:
                        _record_failure(
                            failures,
                            "anchor_error_presence_matches_contact",
                            motion_name,
                            frame_index,
                            f"side={side}, contact={state}, error={error}",
                        )
                pre_depth = float(row["contact_pre_max_ground_penetration_m"])
                post_depth = float(row["contact_post_max_ground_penetration_m"])
                requested = float(row["contact_requested_root_lift_m"])
                applied = float(row["contact_applied_root_lift_m"])
                clipped = _as_bool(row["contact_root_lift_clipped"])
                root_before = float(row["contact_root_z_before_m"])
                root_after = float(row["contact_root_z_after_m"])
                if applied < -tolerance or applied > float(contact_config["max_root_lift_m"]) + tolerance:
                    _record_failure(
                        failures,
                        "root_lift_bounded",
                        motion_name,
                        frame_index,
                        f"applied={applied}",
                    )
                expected_requested = (
                    max(0.0, pre_depth - float(contact_config["target_max_ground_penetration_m"]))
                    if policy == "feet_only"
                    else 0.0
                )
                if not np.isclose(requested, expected_requested, atol=tolerance, rtol=0.0):
                    _record_failure(
                        failures,
                        "requested_lift_matches_penetration",
                        motion_name,
                        frame_index,
                        f"actual={requested}, expected={expected_requested}",
                    )
                delta_lift = applied - previous_lift
                if delta_lift > float(contact_config["max_root_lift_rise_per_frame_m"]) + tolerance:
                    _record_failure(
                        failures,
                        "root_lift_rise_bounded",
                        motion_name,
                        frame_index,
                        f"delta={delta_lift}",
                    )
                if -delta_lift > float(contact_config["max_root_lift_release_per_frame_m"]) + tolerance:
                    _record_failure(
                        failures,
                        "root_lift_release_bounded",
                        motion_name,
                        frame_index,
                        f"delta={delta_lift}",
                    )
                previous_lift = applied
                if not np.isclose(root_after - root_before, applied, atol=tolerance, rtol=0.0):
                    _record_failure(
                        failures,
                        "root_z_delta_matches_applied_lift",
                        motion_name,
                        frame_index,
                        f"delta={root_after-root_before}, applied={applied}",
                    )
                for side in ("left", "right"):
                    sole_delta = (
                        float(row[f"contact_post_{side}_sole_height_m"])
                        - float(row[f"contact_pre_{side}_sole_height_m"])
                    )
                    if not np.isclose(sole_delta, applied, atol=tolerance, rtol=0.0):
                        _record_failure(
                            failures,
                            "sole_delta_matches_applied_lift",
                            motion_name,
                            frame_index,
                            f"side={side}, delta={sole_delta}, applied={applied}",
                        )
                if post_depth > pre_depth + tolerance:
                    _record_failure(
                        failures,
                        "root_lift_does_not_increase_penetration",
                        motion_name,
                        frame_index,
                        f"pre={pre_depth}, post={post_depth}",
                    )
                if policy == "floor_motion" and (
                    left
                    or right
                    or active_anchor_count != 0
                    or requested != 0.0
                    or applied != 0.0
                    or clipped
                ):
                    _record_failure(
                        failures,
                        "floor_motion_intervention_disabled",
                        motion_name,
                        frame_index,
                        "nonzero floor_motion intervention",
                    )

                human_contact = left or right
                sequence_contact_frames += int(human_contact)
                sequence_anchor_frames += int(active_anchor_count > 0)
                sequence_correction_frames += int(applied > 0.0)
                stats["human_contact_frame_count"] += int(human_contact)
                stats["anchor_active_frame_count"] += int(active_anchor_count > 0)
                stats["root_correction_frame_count"] += int(applied > 0.0)
                stats["root_lift_clipped_frame_count"] += int(clipped)
                sequence_max_lift = max(sequence_max_lift, applied)
                sequence_max_pre = max(sequence_max_pre, pre_depth)
                sequence_max_post = max(sequence_max_post, post_depth)
                stats["max_applied_root_lift_m"] = max(
                    stats["max_applied_root_lift_m"], applied
                )
                stats["max_pre_ground_penetration_m"] = max(
                    stats["max_pre_ground_penetration_m"], pre_depth
                )
                stats["max_post_ground_penetration_m"] = max(
                    stats["max_post_ground_penetration_m"], post_depth
                )
                if left_error is not None:
                    stats["max_left_anchor_error_m"] = max(
                        stats["max_left_anchor_error_m"], left_error
                    )
                if right_error is not None:
                    stats["max_right_anchor_error_m"] = max(
                        stats["max_right_anchor_error_m"], right_error
                    )
            except (KeyError, TypeError, ValueError) as error:
                _record_failure(
                    failures,
                    "diagnostic_row_parse",
                    motion_name,
                    expected_index,
                    str(error),
                )

        expected_aggregates = {
            "human_contact_frame_count": sequence_contact_frames,
            "anchor_active_frame_count": sequence_anchor_frames,
            "root_correction_frame_count": sequence_correction_frames,
            "max_applied_root_lift_m": sequence_max_lift,
            "max_pre_ground_penetration_m": sequence_max_pre,
            "max_post_ground_penetration_m": sequence_max_post,
        }
        for key, actual in expected_aggregates.items():
            expected = entry[key]
            equal = (
                int(expected) == int(actual)
                if key.endswith("frame_count")
                else np.isclose(float(expected), float(actual), atol=tolerance, rtol=0.0)
            )
            if not equal:
                manifest_aggregate_failures.append(
                    {
                        "motion_name": motion_name,
                        "field": key,
                        "manifest": expected,
                        "diagnostic": actual,
                    }
                )
        if policy == "floor_motion" and entry["floor_motion_noop_max_abs"] != 0.0:
            manifest_aggregate_failures.append(
                {
                    "motion_name": motion_name,
                    "field": "floor_motion_noop_max_abs",
                    "manifest": entry["floor_motion_noop_max_abs"],
                    "expected": 0.0,
                }
            )

    if manifest_aggregate_failures:
        failures["manifest_aggregates_match_diagnostics"] = {
            "count": len(manifest_aggregate_failures),
            "examples": manifest_aggregate_failures[:5],
        }
    invariant_failure_count = sum(item["count"] for item in failures.values())
    return {
        "schema_version": 1,
        "ok": bool(base["ok"] and invariant_failure_count == 0),
        "base_integrity_audit": base,
        "contact_invariants": {
            "ok": invariant_failure_count == 0,
            "failure_count": invariant_failure_count,
            "failures": failures,
            "policy_statistics": policy_stats,
            "numerical_tolerance": tolerance,
        },
    }
