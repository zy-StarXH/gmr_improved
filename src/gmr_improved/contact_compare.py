"""Preregistered paired A2/A3 comparison for Contact-GMR."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .collision_compare import _bool_series, _bootstrap_mean_delta


PAIRED_METRICS = (
    "joint_jump_rate",
    "joint_jump_count",
    "joint_step_p95_rad",
    "joint_step_max_rad",
    "joint_vel_p95_rad_s",
    "joint_vel_max_rad_s",
    "velocity_violation_frame_rate",
    "velocity_violation_frame_count",
    "near_limit_2pct_frame_rate",
    "joint_limit_violation_frame_rate",
    "joint_acc_p95_rad_s2",
    "joint_jerk_p95_rad_s3",
    "root_acc_p95_m_s2",
    "root_jerk_p95_m_s3",
    "self_collision_nonhand_frame_rate",
    "self_collision_nonhand_event_count",
    "ground_contact_frame_rate",
    "ground_penetration_frame_rate",
    "ground_penetration_frame_count",
    "ground_penetration_event_count",
    "severe_ground_penetration_frame_rate",
    "severe_ground_penetration_frame_count",
    "undesired_ground_contact_frame_rate",
    "undesired_ground_contact_frame_count",
    "undesired_ground_contact_event_count",
    "left_contact_proxy_rate",
    "right_contact_proxy_rate",
    "left_contact_proxy_mismatch_frame_rate",
    "right_contact_proxy_mismatch_frame_rate",
    "foot_slide_frame_rate",
    "foot_slide_frame_count",
    "foot_slide_event_count",
    "foot_slide_speed_p95_m_s",
    "foot_slide_speed_max_m_s",
    "airborne_frame_rate",
    "keybody_pos_error_mean_m",
    "keybody_pos_error_p95_m",
    "end_effector_pos_error_mean_m",
    "end_effector_pos_error_p95_m",
    "link_orientation_error_mean_deg",
    "link_orientation_error_p95_deg",
    "fidelity_pass_frame_rate",
)

RATE_WEIGHTS = {
    "joint_jump_rate": "derivative",
    "velocity_violation_frame_rate": "derivative",
    "near_limit_2pct_frame_rate": "frame",
    "joint_limit_violation_frame_rate": "frame",
    "self_collision_nonhand_frame_rate": "frame",
    "ground_contact_frame_rate": "frame",
    "ground_penetration_frame_rate": "frame",
    "severe_ground_penetration_frame_rate": "frame",
    "undesired_ground_contact_frame_rate": "frame",
    "left_contact_proxy_rate": "frame",
    "right_contact_proxy_rate": "frame",
    "left_contact_proxy_mismatch_frame_rate": "frame",
    "right_contact_proxy_mismatch_frame_rate": "frame",
    "foot_slide_frame_rate": "frame",
    "airborne_frame_rate": "frame",
    "fidelity_pass_frame_rate": "fidelity",
}

COUNT_METRICS = {
    metric
    for metric in PAIRED_METRICS
    if metric.endswith("_count")
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Comparison output must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _weighted_rate(frame: pd.DataFrame, metric: str) -> float:
    kind = RATE_WEIGHTS[metric]
    if kind == "derivative":
        weights = frame["num_frames"].to_numpy(dtype=np.float64) - 1.0
    elif kind == "fidelity":
        weights = frame["fidelity_aligned_frame_count"].to_numpy(dtype=np.float64)
    else:
        weights = frame["num_frames"].to_numpy(dtype=np.float64)
    values = frame[metric].to_numpy(dtype=np.float64)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0.0)
    if not valid.any():
        return float("nan")
    return float(np.average(values[valid], weights=weights[valid]))


def _aggregate(frame: pd.DataFrame, metric: str) -> float:
    if metric in RATE_WEIGHTS:
        return _weighted_rate(frame, metric)
    values = frame[metric].to_numpy(dtype=np.float64)
    if metric in COUNT_METRICS:
        return float(np.nansum(values))
    return float(np.nanmean(values))


def _cohort_metrics(a2: pd.DataFrame, a3: pd.DataFrame) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for metric in PAIRED_METRICS:
        before = _aggregate(a2, metric)
        after = _aggregate(a3, metric)
        result[metric] = {"a2": before, "a3": after, "delta": after - before}
    return result


def compare_contact_results(
    config_path: str | Path,
    a2_summary_path: str | Path,
    a3_summary_path: str | Path,
    a3_manifest_path: str | Path,
    output_dir: str | Path,
) -> Path:
    config_file = Path(config_path).expanduser().resolve()
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    a2_path = Path(a2_summary_path).expanduser().resolve()
    a3_path = Path(a3_summary_path).expanduser().resolve()
    manifest_path = Path(a3_manifest_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    a2_raw = pd.read_csv(a2_path)
    a3_raw = pd.read_csv(a3_path)
    metadata = {
        "motion_name",
        "motion_category",
        "contact_policy",
        "source_bvh",
        "num_frames",
        "fidelity_status",
        "fidelity_aligned_frame_count",
        "fidelity_source_bvh_sha256",
        "hard_fail",
    }
    required = metadata | set(PAIRED_METRICS)
    for label, frame in (("A2", a2_raw), ("A3", a3_raw)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} summary is missing columns: {missing}")
        if frame["motion_name"].duplicated().any():
            raise ValueError(f"{label} summary contains duplicate motions")
    if set(a2_raw["motion_name"]) != set(a3_raw["motion_name"]):
        raise ValueError("A2/A3 motion-name sets do not match")
    a2 = a2_raw.set_index("motion_name").sort_index()
    a3 = a3_raw.set_index("motion_name").sort_index()
    for column in (
        "motion_category",
        "contact_policy",
        "source_bvh",
        "num_frames",
        "fidelity_aligned_frame_count",
        "fidelity_source_bvh_sha256",
    ):
        if not a2[column].equals(a3[column]):
            raise ValueError(f"A2/A3 metadata mismatch in {column}")
    for label, frame in (("A2", a2), ("A3", a3)):
        if not (frame["fidelity_status"] == "enabled_verified").all():
            raise ValueError(f"{label} fidelity is not enabled_verified for every motion")

    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not run_manifest.get("complete") or not run_manifest.get("formal_run"):
        raise ValueError("A3 generation manifest is not a complete formal run")
    if run_manifest.get("formal_role") != config["formal_role"]:
        raise ValueError("A3 manifest formal role differs from comparison config")
    floor_noop = {
        row["motion_name"]: row.get("floor_motion_noop_max_abs")
        for row in run_manifest.get("inputs", [])
        if row.get("contact_policy") == "floor_motion"
    }
    expected_floor = set(a2.index[a2["contact_policy"] == "floor_motion"])
    if set(floor_noop) != expected_floor or any(value != 0.0 for value in floor_noop.values()):
        raise ValueError(f"floor_motion exact no-op audit failed: {floor_noop}")

    paired_columns: dict[str, pd.Series] = {
        "motion_category": a2["motion_category"],
        "contact_policy": a2["contact_policy"],
        "num_frames": a2["num_frames"],
    }
    for metric in PAIRED_METRICS:
        paired_columns[f"a2_{metric}"] = a2[metric]
        paired_columns[f"a3_{metric}"] = a3[metric]
        paired_columns[f"delta_{metric}"] = a3[metric] - a2[metric]
    paired = pd.DataFrame(paired_columns, index=a2.index)
    paired.reset_index().to_csv(destination / "paired_motion_metrics.csv", index=False)

    cohort_frames = {
        "overall": (a2.reset_index(), a3.reset_index()),
        "feet_only": (
            a2[a2["contact_policy"] == "feet_only"].reset_index(),
            a3[a3["contact_policy"] == "feet_only"].reset_index(),
        ),
        "floor_motion": (
            a2[a2["contact_policy"] == "floor_motion"].reset_index(),
            a3[a3["contact_policy"] == "floor_motion"].reset_index(),
        ),
    }
    cohorts = {
        name: _cohort_metrics(before, after)
        for name, (before, after) in cohort_frames.items()
    }
    policy_rows = []
    for name, values in cohorts.items():
        before = cohort_frames[name][0]
        for metric, item in values.items():
            policy_rows.append(
                {
                    "cohort": name,
                    "motion_count": len(before),
                    "frame_count": int(before["num_frames"].sum()),
                    "metric": metric,
                    **item,
                }
            )
    pd.DataFrame(policy_rows).to_csv(destination / "policy_metrics.csv", index=False)

    feet_index = paired["contact_policy"] == "feet_only"
    bootstrap = {
        metric: _bootstrap_mean_delta(
            paired.loc[feet_index, f"delta_{metric}"].to_numpy(dtype=np.float64),
            seed=20260806,
            resamples=10_000,
        )
        for metric in (
            "foot_slide_frame_rate",
            "ground_penetration_frame_rate",
            "severe_ground_penetration_frame_rate",
            "undesired_ground_contact_frame_rate",
            "fidelity_pass_frame_rate",
        )
    }
    a2_hard = _bool_series(a2["hard_fail"])
    a3_hard = _bool_series(a3["hard_fail"])
    new_hard_fail_names = sorted(a2.index[(~a2_hard) & a3_hard].tolist())
    acceptance_config = config["acceptance"]
    feet_metrics = cohorts["feet_only"]
    overall_metrics = cohorts["overall"]
    strict_checks = {
        metric: feet_metrics[metric]["delta"] < 0.0
        for metric in acceptance_config["require_strict_improvement"]
    }
    nonincrease_checks = {
        metric: feet_metrics[metric]["delta"] <= 0.0
        for metric in acceptance_config["require_nonincrease"]
    }
    zero_checks = {
        metric: bool(
            np.isclose(overall_metrics[metric]["a2"], 0.0, atol=1e-15, rtol=0.0)
            and np.isclose(overall_metrics[metric]["a3"], 0.0, atol=1e-15, rtol=0.0)
        )
        for metric in ("joint_jump_rate", "velocity_violation_frame_rate")
    }
    fidelity_decline = -overall_metrics["fidelity_pass_frame_rate"]["delta"]
    max_fidelity_decline = float(
        acceptance_config[
            "maximum_overall_fidelity_pass_rate_decline_relative_to_a2"
        ]
    )
    collision_increase = overall_metrics["self_collision_nonhand_frame_rate"]["delta"]
    max_collision_increase = float(
        acceptance_config["maximum_overall_self_collision_nonhand_rate_increase"]
    )
    acceptance = {
        "strict_feet_only_improvements": strict_checks,
        "feet_only_nonincrease": nonincrease_checks,
        "floor_motion_exact_noop": True,
        "floor_motion_noop_max_abs_by_motion": floor_noop,
        "preserved_zero_joint_jump_and_velocity_violation": zero_checks,
        "no_new_hard_fail": not new_hard_fail_names,
        "new_hard_fail_motions": new_hard_fail_names,
        "overall_fidelity_pass_rate_decline": fidelity_decline,
        "maximum_allowed_fidelity_decline": max_fidelity_decline,
        "fidelity_gate_pass": fidelity_decline <= max_fidelity_decline,
        "overall_self_collision_nonhand_rate_increase": collision_increase,
        "maximum_allowed_self_collision_increase": max_collision_increase,
        "collision_preservation_gate_pass": collision_increase <= max_collision_increase,
    }
    acceptance["contact_gate_pass"] = bool(
        all(strict_checks.values())
        and all(nonincrease_checks.values())
        and all(zero_checks.values())
        and acceptance["no_new_hard_fail"]
        and acceptance["fidelity_gate_pass"]
        and acceptance["collision_preservation_gate_pass"]
    )
    summary = {
        "schema_version": 1,
        "comparison": f"A2_Collision_GMR_vs_A3_Contact_GMR_{config['formal_role']}",
        "motion_count": len(paired),
        "frame_count": int(a2["num_frames"].sum()),
        "uncalibrated_quality_score_used": False,
        "cohort_metrics": cohorts,
        "feet_only_paired_motion_bootstrap_mean_delta": bootstrap,
        "hard_fail": {
            "a2_count": int(a2_hard.sum()),
            "a3_count": int(a3_hard.sum()),
            "new_hard_fail_motions": new_hard_fail_names,
        },
        "acceptance": acceptance,
        "inputs": {
            "config": {"path": str(config_file), "sha256": _sha256(config_file)},
            "a2_summary": {"path": str(a2_path), "sha256": _sha256(a2_path)},
            "a3_summary": {"path": str(a3_path), "sha256": _sha256(a3_path)},
            "a3_manifest": {"path": str(manifest_path), "sha256": _sha256(manifest_path)},
        },
    }
    output = destination / "comparison_summary.json"
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = f"""# Contact-GMR {config['formal_role']} 配对结果

本报告比较 A2 Collision-GMR 与 A3 Contact-GMR，共 {len(paired)} 条、{int(a2['num_frames'].sum()):,} 帧；主要接触门控只在 `feet_only` 队列计算，`floor_motion` 要求逐元素 no-op。未使用未校准综合分数。

| feet_only 指标 | A2 | A3 | A3-A2 |
|---|---:|---:|---:|
| `foot_slide_frame_rate` | {feet_metrics['foot_slide_frame_rate']['a2']:.9g} | {feet_metrics['foot_slide_frame_rate']['a3']:.9g} | {feet_metrics['foot_slide_frame_rate']['delta']:.9g} |
| `ground_penetration_frame_rate` | {feet_metrics['ground_penetration_frame_rate']['a2']:.9g} | {feet_metrics['ground_penetration_frame_rate']['a3']:.9g} | {feet_metrics['ground_penetration_frame_rate']['delta']:.9g} |
| `severe_ground_penetration_frame_rate` | {feet_metrics['severe_ground_penetration_frame_rate']['a2']:.9g} | {feet_metrics['severe_ground_penetration_frame_rate']['a3']:.9g} | {feet_metrics['severe_ground_penetration_frame_rate']['delta']:.9g} |
| `undesired_ground_contact_frame_rate` | {feet_metrics['undesired_ground_contact_frame_rate']['a2']:.9g} | {feet_metrics['undesired_ground_contact_frame_rate']['a3']:.9g} | {feet_metrics['undesired_ground_contact_frame_rate']['delta']:.9g} |

- 新增 hard-fail：{new_hard_fail_names or '无'}
- 总体 fidelity pass rate 下降：{fidelity_decline:.9g}
- 总体非手部碰撞帧率增加：{collision_increase:.9g}
- Contact 门控：{'通过' if acceptance['contact_gate_pass'] else '未通过'}

逐动作和分 policy 结果见同目录 CSV；门控通过也不代表动力学执行或下游学习已经验证。
"""
    (destination / "CONTACT_GMR_COMPARISON_REPORT.md").write_text(report, encoding="utf-8")
    manifest = {
        "complete": True,
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": _sha256(Path(__file__).resolve())},
        "files": [
            {"path": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in sorted(destination.iterdir())
            if path.name != "comparison_manifest.json"
        ],
    }
    (destination / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
