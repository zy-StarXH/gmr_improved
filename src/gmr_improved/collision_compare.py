"""Preregistered paired A1/A2 comparison for Collision-GMR development data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


PAIRED_METRICS = (
    "joint_jump_rate",
    "joint_jump_count",
    "joint_step_p95_rad",
    "joint_step_max_rad",
    "joint_vel_p95_rad_s",
    "joint_vel_max_rad_s",
    "velocity_violation_frame_rate",
    "velocity_violation_frame_count",
    "near_limit_0p05rad_frame_rate",
    "near_limit_2pct_frame_rate",
    "joint_limit_violation_frame_rate",
    "joint_limit_violation_frame_count",
    "joint_acc_p95_rad_s2",
    "joint_jerk_p95_rad_s3",
    "self_collision_any_frame_rate",
    "self_collision_nonhand_frame_rate",
    "self_collision_nonhand_frame_count",
    "self_collision_event_count",
    "self_collision_nonhand_event_count",
    "max_self_collision_penetration_m",
    "ground_penetration_frame_rate",
    "ground_penetration_event_count",
    "severe_ground_penetration_frame_rate",
    "undesired_ground_contact_frame_rate",
    "undesired_ground_contact_event_count",
    "foot_slide_frame_rate",
    "foot_slide_event_count",
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
    "near_limit_0p05rad_frame_rate": "frame",
    "near_limit_2pct_frame_rate": "frame",
    "joint_limit_violation_frame_rate": "frame",
    "self_collision_any_frame_rate": "frame",
    "self_collision_nonhand_frame_rate": "frame",
    "ground_penetration_frame_rate": "frame",
    "severe_ground_penetration_frame_rate": "frame",
    "undesired_ground_contact_frame_rate": "frame",
    "foot_slide_frame_rate": "frame",
    "fidelity_pass_frame_rate": "fidelity",
}

COUNT_METRICS = {
    "joint_jump_count",
    "velocity_violation_frame_count",
    "joint_limit_violation_frame_count",
    "self_collision_nonhand_frame_count",
    "self_collision_event_count",
    "self_collision_nonhand_event_count",
    "ground_penetration_event_count",
    "undesired_ground_contact_event_count",
    "foot_slide_event_count",
}

PRIMARY_RATE = "self_collision_nonhand_frame_rate"
PRIMARY_EVENTS = "self_collision_nonhand_event_count"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Comparison output directory must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    mapping = {"true": True, "false": False}
    if not normalized.isin(mapping).all():
        raise ValueError(f"Invalid boolean values: {sorted(normalized.unique())}")
    return normalized.map(mapping).astype(bool)


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


def _bootstrap_mean_delta(
    deltas: np.ndarray, *, seed: int = 20260806, resamples: int = 10_000
) -> dict[str, float | int]:
    values = np.asarray(deltas, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {
            "motion_count": 0,
            "mean_delta": float("nan"),
            "ci95_low": float("nan"),
            "ci95_high": float("nan"),
        }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(resamples, values.size))
    samples = values[indices].mean(axis=1)
    return {
        "motion_count": int(values.size),
        "mean_delta": float(values.mean()),
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
    }


def compare_collision_results(
    config_path: str | Path,
    a1_summary_path: str | Path,
    a2_summary_path: str | Path,
    output_dir: str | Path,
) -> Path:
    """Compare frozen Temporal-GMR A1 and Collision-GMR A2 summaries."""

    config_file = Path(config_path).expanduser().resolve()
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    a1_path = Path(a1_summary_path).expanduser().resolve()
    a2_path = Path(a2_summary_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)

    a1_raw = pd.read_csv(a1_path)
    a2_raw = pd.read_csv(a2_path)
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
    for label, frame in (("A1", a1_raw), ("A2", a2_raw)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} summary is missing columns: {missing}")
        if frame["motion_name"].duplicated().any():
            raise ValueError(f"{label} summary contains duplicate motion names")
    if set(a1_raw["motion_name"]) != set(a2_raw["motion_name"]):
        raise ValueError("A1/A2 motion-name sets do not match")

    a1 = a1_raw.set_index("motion_name").sort_index()
    a2 = a2_raw.set_index("motion_name").sort_index()
    for column in (
        "motion_category",
        "contact_policy",
        "source_bvh",
        "num_frames",
        "fidelity_aligned_frame_count",
        "fidelity_source_bvh_sha256",
    ):
        if not a1[column].equals(a2[column]):
            raise ValueError(f"A1/A2 metadata mismatch in {column}")
    for label, frame in (("A1", a1), ("A2", a2)):
        statuses = frame["fidelity_status"].value_counts().to_dict()
        if not (frame["fidelity_status"] == "enabled_verified").all():
            raise ValueError(f"{label} fidelity is not verified for every motion: {statuses}")

    paired_columns: dict[str, pd.Series] = {
        "motion_category": a1["motion_category"],
        "contact_policy": a1["contact_policy"],
        "num_frames": a1["num_frames"],
    }
    for metric in PAIRED_METRICS:
        paired_columns[f"a1_{metric}"] = a1[metric]
        paired_columns[f"a2_{metric}"] = a2[metric]
        paired_columns[f"delta_{metric}"] = a2[metric] - a1[metric]
    paired = pd.DataFrame(paired_columns, index=a1.index)
    paired.reset_index().to_csv(destination / "paired_motion_metrics.csv", index=False)

    cohort_metrics: dict[str, dict[str, float]] = {}
    for metric in PAIRED_METRICS:
        a1_value = _aggregate(a1.reset_index(), metric)
        a2_value = _aggregate(a2.reset_index(), metric)
        cohort_metrics[metric] = {
            "a1": a1_value,
            "a2": a2_value,
            "delta": a2_value - a1_value,
        }

    category_rows: list[dict[str, Any]] = []
    for category in sorted(a1["motion_category"].unique()):
        a1_category = a1[a1["motion_category"] == category].reset_index()
        a2_category = a2[a2["motion_category"] == category].reset_index()
        for metric in PAIRED_METRICS:
            a1_value = _aggregate(a1_category, metric)
            a2_value = _aggregate(a2_category, metric)
            category_rows.append(
                {
                    "motion_category": category,
                    "motion_count": len(a1_category),
                    "frame_count": int(a1_category["num_frames"].sum()),
                    "metric": metric,
                    "a1": a1_value,
                    "a2": a2_value,
                    "delta": a2_value - a1_value,
                }
            )
    pd.DataFrame(category_rows).to_csv(destination / "category_metrics.csv", index=False)

    bootstrap = {
        metric: _bootstrap_mean_delta(
            paired[f"delta_{metric}"].to_numpy(dtype=np.float64)
        )
        for metric in (
            PRIMARY_RATE,
            PRIMARY_EVENTS,
            "fidelity_pass_frame_rate",
            "joint_jump_rate",
            "velocity_violation_frame_rate",
        )
    }
    a1_hard = _bool_series(a1["hard_fail"])
    a2_hard = _bool_series(a2["hard_fail"])
    new_hard_fail_names = sorted(a1.index[(~a1_hard) & a2_hard].tolist())

    max_decline = float(
        config["acceptance"][
            "maximum_overall_fidelity_pass_rate_decline_relative_to_a1"
        ]
    )
    fidelity_decline = -cohort_metrics["fidelity_pass_frame_rate"]["delta"]
    primary_checks = {
        PRIMARY_RATE: cohort_metrics[PRIMARY_RATE]["delta"] < 0.0,
        PRIMARY_EVENTS: cohort_metrics[PRIMARY_EVENTS]["delta"] < 0.0,
    }
    zero_checks = {
        metric: bool(
            np.isclose(cohort_metrics[metric]["a1"], 0.0, atol=1e-15, rtol=0.0)
            and np.isclose(cohort_metrics[metric]["a2"], 0.0, atol=1e-15, rtol=0.0)
        )
        for metric in ("joint_jump_rate", "velocity_violation_frame_rate")
    }
    acceptance = {
        "strict_primary_improvements": primary_checks,
        "no_new_hard_fail": not new_hard_fail_names,
        "new_hard_fail_motions": new_hard_fail_names,
        "preserved_zero_joint_jump_and_velocity_violation": zero_checks,
        "overall_fidelity_pass_rate_decline": fidelity_decline,
        "maximum_allowed_fidelity_decline": max_decline,
        "fidelity_gate_pass": fidelity_decline <= max_decline,
    }
    acceptance["development_gate_pass"] = bool(
        all(primary_checks.values())
        and acceptance["no_new_hard_fail"]
        and all(zero_checks.values())
        and acceptance["fidelity_gate_pass"]
    )

    summary = {
        "schema_version": 1,
        "comparison": "A1_Temporal_GMR_v2_vs_A2_Collision_GMR_v1",
        "motion_count": int(len(paired)),
        "frame_count": int(a1["num_frames"].sum()),
        "uncalibrated_quality_score_used": False,
        "cohort_metrics": cohort_metrics,
        "paired_motion_bootstrap_mean_delta": bootstrap,
        "hard_fail": {
            "a1_count": int(a1_hard.sum()),
            "a2_count": int(a2_hard.sum()),
            "new_hard_fail_motions": new_hard_fail_names,
        },
        "acceptance": acceptance,
        "inputs": {
            "config": {"path": str(config_file), "sha256": _sha256(config_file)},
            "a1_summary": {"path": str(a1_path), "sha256": _sha256(a1_path)},
            "a2_summary": {"path": str(a2_path), "sha256": _sha256(a2_path)},
        },
    }
    summary_path = destination / "comparison_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    primary_rate = cohort_metrics[PRIMARY_RATE]
    primary_events = cohort_metrics[PRIMARY_EVENTS]
    fidelity = cohort_metrics["fidelity_pass_frame_rate"]
    report = f"""# Collision-GMR 冻结开发集配对结果

本报告比较同一组 {len(paired)} 条、{int(a1['num_frames'].sum()):,} 帧 LAFAN1 动作的 A1 Temporal-GMR v2 与 A2 Collision-GMR v1。所有基础指标独立报告，未使用未校准 `quality_score`。

| 指标 | A1 | A2 | A2-A1 |
|---|---:|---:|---:|
| `self_collision_nonhand_frame_rate` | {primary_rate['a1']:.9g} | {primary_rate['a2']:.9g} | {primary_rate['delta']:.9g} |
| `self_collision_nonhand_event_count` | {primary_events['a1']:.9g} | {primary_events['a2']:.9g} | {primary_events['delta']:.9g} |
| `joint_jump_rate` | {cohort_metrics['joint_jump_rate']['a1']:.9g} | {cohort_metrics['joint_jump_rate']['a2']:.9g} | {cohort_metrics['joint_jump_rate']['delta']:.9g} |
| `velocity_violation_frame_rate` | {cohort_metrics['velocity_violation_frame_rate']['a1']:.9g} | {cohort_metrics['velocity_violation_frame_rate']['a2']:.9g} | {cohort_metrics['velocity_violation_frame_rate']['delta']:.9g} |
| `fidelity_pass_frame_rate` | {fidelity['a1']:.9g} | {fidelity['a2']:.9g} | {fidelity['delta']:.9g} |

- 新增 hard-fail 动作：{new_hard_fail_names or '无'}
- fidelity pass rate 下降：{fidelity_decline:.9g}（门限 {max_decline:.9g}）
- 开发门控：{'通过' if acceptance['development_gate_pass'] else '未通过'}

该门控只检验冻结开发集上的预注册工程标准；不代表独立留出集或机器人学习效果。完整总体指标、bootstrap 区间见 `comparison_summary.json`，逐动作和逐类别结果分别见 `paired_motion_metrics.csv` 与 `category_metrics.csv`。
"""
    (destination / "COLLISION_GMR_DEVELOPMENT_REPORT.md").write_text(
        report, encoding="utf-8"
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
            if path.name != "comparison_manifest.json"
        ],
    }
    (destination / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
