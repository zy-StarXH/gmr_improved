"""Predefined A0/A1 paired comparison for Temporal-GMR development results."""

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
    "joint_step_p95_rad",
    "joint_step_max_rad",
    "joint_vel_p95_rad_s",
    "joint_vel_max_rad_s",
    "velocity_violation_frame_rate",
    "near_limit_0p05rad_frame_rate",
    "near_limit_2pct_frame_rate",
    "joint_limit_violation_frame_rate",
    "joint_acc_p95_rad_s2",
    "joint_jerk_p95_rad_s3",
    "self_collision_nonhand_frame_rate",
    "ground_penetration_frame_rate",
    "severe_ground_penetration_frame_rate",
    "undesired_ground_contact_frame_rate",
    "foot_slide_frame_rate",
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
    "self_collision_nonhand_frame_rate": "frame",
    "ground_penetration_frame_rate": "frame",
    "severe_ground_penetration_frame_rate": "frame",
    "undesired_ground_contact_frame_rate": "frame",
    "foot_slide_frame_rate": "frame",
    "fidelity_pass_frame_rate": "fidelity",
}

STRICT_IMPROVEMENT_METRICS = (
    "joint_jump_rate",
    "velocity_violation_frame_rate",
    "near_limit_2pct_frame_rate",
)


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
    mapping = {"true": True, "false": False}
    normalized = series.astype(str).str.strip().str.lower()
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


def _bootstrap_mean_delta(
    deltas: np.ndarray, *, seed: int, resamples: int
) -> dict[str, float | int]:
    values = np.asarray(deltas, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"motion_count": 0, "mean_delta": float("nan"), "ci95_low": float("nan"), "ci95_high": float("nan")}
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(resamples, values.size))
    samples = values[indices].mean(axis=1)
    return {
        "motion_count": int(values.size),
        "mean_delta": float(values.mean()),
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
    }


def compare_temporal_results(
    config_path: str | Path,
    temporal_summary_path: str | Path,
    output_dir: str | Path,
) -> Path:
    config_file = Path(config_path).expanduser().resolve()
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    baseline_path = Path(config["paths"]["baseline_quality_summary"]).expanduser().resolve()
    temporal_path = Path(temporal_summary_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    baseline = pd.read_csv(baseline_path)
    temporal = pd.read_csv(temporal_path)
    required = {
        "motion_name", "motion_category", "contact_policy", "num_frames",
        "fidelity_aligned_frame_count", "hard_fail", *PAIRED_METRICS,
    }
    for label, frame in (("A0", baseline), ("A1", temporal)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} summary is missing columns: {missing}")
        if frame["motion_name"].duplicated().any():
            raise ValueError(f"{label} summary contains duplicate motion names")
    if set(baseline["motion_name"]) != set(temporal["motion_name"]):
        raise ValueError("A0/A1 motion-name sets do not match")

    base = baseline.set_index("motion_name").sort_index()
    temp = temporal.set_index("motion_name").sort_index()
    for column in ("motion_category", "contact_policy", "num_frames"):
        if not base[column].equals(temp[column]):
            raise ValueError(f"A0/A1 metadata mismatch in {column}")
    if not (temp["fidelity_status"] == "enabled_verified").all():
        statuses = temp["fidelity_status"].value_counts().to_dict()
        raise ValueError(f"A1 fidelity is not verified for every motion: {statuses}")

    paired = base[["motion_category", "contact_policy", "num_frames"]].copy()
    for metric in PAIRED_METRICS:
        paired[f"a0_{metric}"] = base[metric]
        paired[f"a1_{metric}"] = temp[metric]
        paired[f"delta_{metric}"] = temp[metric] - base[metric]
    paired.reset_index().to_csv(destination / "paired_motion_metrics.csv", index=False)

    cohort_metrics: dict[str, dict[str, float]] = {}
    for metric in PAIRED_METRICS:
        if metric in RATE_WEIGHTS:
            a0 = _weighted_rate(base.reset_index(), metric)
            a1 = _weighted_rate(temp.reset_index(), metric)
        else:
            a0 = float(base[metric].mean())
            a1 = float(temp[metric].mean())
        cohort_metrics[metric] = {"a0": a0, "a1": a1, "delta": a1 - a0}

    bootstrap = {
        metric: _bootstrap_mean_delta(
            paired[f"delta_{metric}"].to_numpy(dtype=np.float64),
            seed=20260805,
            resamples=10_000,
        )
        for metric in STRICT_IMPROVEMENT_METRICS + ("fidelity_pass_frame_rate",)
    }
    base_hard = _bool_series(base["hard_fail"])
    temp_hard = _bool_series(temp["hard_fail"])
    new_hard_fail_names = sorted(base.index[(~base_hard) & temp_hard].tolist())
    fidelity_decline = -cohort_metrics["fidelity_pass_frame_rate"]["delta"]
    improvement_checks = {
        metric: cohort_metrics[metric]["delta"] < 0.0
        for metric in STRICT_IMPROVEMENT_METRICS
    }
    acceptance = {
        "strict_primary_improvements": improvement_checks,
        "no_new_hard_fail": not new_hard_fail_names,
        "new_hard_fail_motions": new_hard_fail_names,
        "overall_fidelity_pass_rate_decline": fidelity_decline,
        "maximum_allowed_fidelity_decline": float(
            config["acceptance"]["maximum_overall_fidelity_pass_rate_decline"]
        ),
        "fidelity_gate_pass": fidelity_decline
        <= float(config["acceptance"]["maximum_overall_fidelity_pass_rate_decline"]),
    }
    acceptance["development_gate_pass"] = bool(
        all(improvement_checks.values())
        and acceptance["no_new_hard_fail"]
        and acceptance["fidelity_gate_pass"]
    )
    summary = {
        "schema_version": 1,
        "comparison": "A0_original_GMR_vs_A1_Temporal_GMR",
        "motion_count": int(len(paired)),
        "frame_count": int(base["num_frames"].sum()),
        "uncalibrated_quality_score_used": False,
        "cohort_metrics": cohort_metrics,
        "paired_motion_bootstrap_mean_delta": bootstrap,
        "hard_fail": {
            "a0_count": int(base_hard.sum()),
            "a1_count": int(temp_hard.sum()),
            "new_hard_fail_motions": new_hard_fail_names,
        },
        "acceptance": acceptance,
        "inputs": {
            "config": {"path": str(config_file), "sha256": _sha256(config_file)},
            "a0_summary": {"path": str(baseline_path), "sha256": _sha256(baseline_path)},
            "a1_summary": {"path": str(temporal_path), "sha256": _sha256(temporal_path)},
        },
    }
    summary_path = destination / "comparison_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    primary_lines = []
    for metric in STRICT_IMPROVEMENT_METRICS:
        values = cohort_metrics[metric]
        primary_lines.append(
            f"| `{metric}` | {values['a0']:.9g} | {values['a1']:.9g} | {values['delta']:.9g} |"
        )
    fidelity = cohort_metrics["fidelity_pass_frame_rate"]
    report = f"""# Temporal-GMR 冻结开发集配对结果

本报告比较同一组 {len(paired)} 条、{int(base['num_frames'].sum()):,} 帧 LAFAN1 动作的 A0 与 A1。所有基础指标保持独立，未使用未校准 `quality_score`。

| 指标 | A0 | A1 | A1-A0 |
|---|---:|---:|---:|
{chr(10).join(primary_lines)}
| `fidelity_pass_frame_rate` | {fidelity['a0']:.9g} | {fidelity['a1']:.9g} | {fidelity['delta']:.9g} |

- 新增 hard-fail 动作：{new_hard_fail_names or '无'}
- fidelity pass rate 下降：{fidelity_decline:.9g}（门限 0.02）
- 开发门控：{'通过' if acceptance['development_gate_pass'] else '未通过'}

“通过”只表示冻结开发集满足预注册工程门控，不是对冻结正式测试集或下游机器人学习效果的结论。逐动作结果见 `paired_motion_metrics.csv`，配对 motion-level bootstrap 区间和完整指标见 `comparison_summary.json`。
"""
    (destination / "TEMPORAL_GMR_DEVELOPMENT_REPORT.md").write_text(report, encoding="utf-8")
    manifest = {
        "complete": True,
        "files": [
            {"path": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in sorted(destination.iterdir())
            if path.name != "comparison_manifest.json"
        ],
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
    }
    (destination / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path

