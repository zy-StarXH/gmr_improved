"""Paired statistics and preregistered gate for the Temporal-GMR held-out test."""

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

RATE_KINDS = {
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


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Comparison output must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    values = series.astype(str).str.strip().str.lower()
    if not values.isin({"true", "false"}).all():
        raise ValueError(f"Invalid boolean values: {sorted(values.unique())}")
    return values.map({"true": True, "false": False}).astype(bool)


def _weighted_metric(frame: pd.DataFrame, metric: str) -> float:
    kind = RATE_KINDS.get(metric)
    if kind is None:
        values = frame[metric].to_numpy(dtype=np.float64)
        return float(np.nanmean(values))
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


def _bootstrap(
    values: np.ndarray, *, seed: int, resamples: int
) -> dict[str, float | int]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not values.size:
        return {
            "motion_count": 0,
            "mean_delta": float("nan"),
            "ci95_low": float("nan"),
            "ci95_high": float("nan"),
        }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(resamples, values.size))
    means = values[indices].mean(axis=1)
    return {
        "motion_count": int(values.size),
        "mean_delta": float(values.mean()),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
    }


def compare_heldout(
    config_path: str | Path,
    a0_summary_path: str | Path,
    a1_summary_path: str | Path,
    output_dir: str | Path,
) -> Path:
    config_file = Path(config_path).expanduser().resolve()
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    a0_path = Path(a0_summary_path).expanduser().resolve()
    a1_path = Path(a1_summary_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    a0 = pd.read_csv(a0_path)
    a1 = pd.read_csv(a1_path)
    required = {
        "motion_name",
        "motion_category",
        "contact_policy",
        "num_frames",
        "fidelity_aligned_frame_count",
        "fidelity_status",
        "hard_fail",
        "failure_reason_codes",
        *PAIRED_METRICS,
    }
    for label, frame in (("A0", a0), ("A1", a1)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} summary missing columns: {missing}")
        if frame["motion_name"].duplicated().any():
            raise ValueError(f"{label} summary contains duplicate motions")
        if not (frame["fidelity_status"] == "enabled_verified").all():
            raise ValueError(f"{label} does not have verified fidelity for every motion")

    base = a0.set_index("motion_name").sort_index()
    temp = a1.set_index("motion_name").sort_index()
    if set(base.index) != set(temp.index):
        raise ValueError("A0/A1 held-out motion sets differ")
    for column in ("motion_category", "contact_policy", "num_frames"):
        if not base[column].equals(temp[column]):
            raise ValueError(f"A0/A1 metadata mismatch in {column}")
    expected = config["experiment"]
    if len(base) != int(expected["motion_count"]) or int(base["num_frames"].sum()) != int(
        expected["total_frames"]
    ):
        raise ValueError("Held-out summary does not match frozen cohort size")

    paired = base[["motion_category", "contact_policy", "num_frames"]].copy()
    for metric in PAIRED_METRICS:
        paired[f"a0_{metric}"] = base[metric]
        paired[f"a1_{metric}"] = temp[metric]
        paired[f"delta_{metric}"] = temp[metric] - base[metric]
    paired_path = destination / "paired_motion_metrics.csv"
    paired.reset_index().to_csv(paired_path, index=False)

    cohort_metrics: dict[str, dict[str, float]] = {}
    for metric in PAIRED_METRICS:
        baseline_value = _weighted_metric(base.reset_index(), metric)
        temporal_value = _weighted_metric(temp.reset_index(), metric)
        cohort_metrics[metric] = {
            "a0": baseline_value,
            "a1": temporal_value,
            "delta": temporal_value - baseline_value,
        }

    category_rows: list[dict[str, Any]] = []
    for category in sorted(base["motion_category"].unique()):
        a0_category = base[base["motion_category"] == category].reset_index()
        a1_category = temp[temp["motion_category"] == category].reset_index()
        row: dict[str, Any] = {
            "motion_category": category,
            "motion_count": len(a0_category),
            "frame_count": int(a0_category["num_frames"].sum()),
        }
        for metric in PAIRED_METRICS:
            a0_value = _weighted_metric(a0_category, metric)
            a1_value = _weighted_metric(a1_category, metric)
            row[f"a0_{metric}"] = a0_value
            row[f"a1_{metric}"] = a1_value
            row[f"delta_{metric}"] = a1_value - a0_value
        category_rows.append(row)
    pd.DataFrame(category_rows).to_csv(destination / "category_metrics.csv", index=False)

    strict_metrics = tuple(config["acceptance"]["strict_improvement_metrics"])
    seed = int(config["acceptance"]["bootstrap_seed"])
    resamples = int(config["acceptance"]["bootstrap_resamples"])
    bootstrap_metrics = (*strict_metrics, "fidelity_pass_frame_rate")
    bootstrap = {
        metric: _bootstrap(
            paired[f"delta_{metric}"].to_numpy(dtype=np.float64),
            seed=seed,
            resamples=resamples,
        )
        for metric in bootstrap_metrics
    }
    a0_hard = _bool_series(base["hard_fail"])
    a1_hard = _bool_series(temp["hard_fail"])
    new_hard = sorted(base.index[(~a0_hard) & a1_hard].tolist())
    resolved_hard = sorted(base.index[a0_hard & (~a1_hard)].tolist())
    hard_transitions = pd.DataFrame(
        {
            "motion_name": base.index,
            "a0_hard_fail": a0_hard.to_numpy(),
            "a1_hard_fail": a1_hard.to_numpy(),
            "transition": np.select(
                [
                    ((~a0_hard) & a1_hard).to_numpy(),
                    (a0_hard & (~a1_hard)).to_numpy(),
                ],
                ["new_hard_fail", "resolved_hard_fail"],
                default="unchanged",
            ),
            "a0_failure_reason_codes": base["failure_reason_codes"].to_numpy(),
            "a1_failure_reason_codes": temp["failure_reason_codes"].to_numpy(),
        }
    )
    hard_transitions.to_csv(destination / "hard_fail_transitions.csv", index=False)

    improvements = {
        metric: cohort_metrics[metric]["delta"] < 0.0 for metric in strict_metrics
    }
    fidelity_decline = -cohort_metrics["fidelity_pass_frame_rate"]["delta"]
    fidelity_limit = float(
        config["acceptance"]["maximum_overall_fidelity_pass_rate_decline"]
    )
    acceptance = {
        "strict_primary_improvements": improvements,
        "no_new_hard_fail": not new_hard,
        "new_hard_fail_motions": new_hard,
        "resolved_hard_fail_motions": resolved_hard,
        "overall_fidelity_pass_rate_decline": fidelity_decline,
        "maximum_allowed_fidelity_decline": fidelity_limit,
        "fidelity_gate_pass": fidelity_decline <= fidelity_limit,
    }
    acceptance["heldout_gate_pass"] = bool(
        all(improvements.values())
        and acceptance["no_new_hard_fail"]
        and acceptance["fidelity_gate_pass"]
    )

    result = {
        "schema_version": 1,
        "comparison": "A0_original_GMR_vs_A1_Temporal_GMR_v2_preregistered_heldout",
        "motion_count": int(len(base)),
        "frame_count": int(base["num_frames"].sum()),
        "derivative_interval_count": int((base["num_frames"] - 1).sum()),
        "uncalibrated_quality_score_used": False,
        "cohort_metrics": cohort_metrics,
        "paired_motion_bootstrap_mean_delta": bootstrap,
        "hard_fail": {
            "a0_count": int(a0_hard.sum()),
            "a1_count": int(a1_hard.sum()),
            "new_hard_fail_motions": new_hard,
            "resolved_hard_fail_motions": resolved_hard,
        },
        "acceptance": acceptance,
        "inputs": {
            "config": {"path": str(config_file), "sha256": sha256_file(config_file)},
            "a0_summary": {"path": str(a0_path), "sha256": sha256_file(a0_path)},
            "a1_summary": {"path": str(a1_path), "sha256": sha256_file(a1_path)},
        },
    }
    summary_path = destination / "comparison_summary.json"
    summary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    primary_rows = "\n".join(
        f"| `{metric}` | {cohort_metrics[metric]['a0']:.9g} | "
        f"{cohort_metrics[metric]['a1']:.9g} | {cohort_metrics[metric]['delta']:.9g} |"
        for metric in strict_metrics
    )
    fidelity = cohort_metrics["fidelity_pass_frame_rate"]
    report = f"""# Temporal-GMR v2 预注册独立测试

同一组 {len(base)} 条、{int(base['num_frames'].sum()):,} 帧 held-out 动作的 A0/A1 配对比较。该队列在开发结果前已写入 `PLAN.md`；未使用未校准 `quality_score`。

| 指标 | A0 | A1 | A1-A0 |
|---|---:|---:|---:|
{primary_rows}
| `fidelity_pass_frame_rate` | {fidelity['a0']:.9g} | {fidelity['a1']:.9g} | {fidelity['delta']:.9g} |

- A0/A1 hard-fail：{int(a0_hard.sum())}/{int(a1_hard.sum())}
- 新增 hard-fail：{new_hard or '无'}
- fidelity pass rate 下降：{fidelity_decline:.9g}（上限 {fidelity_limit:.9g}）
- held-out 门控：{'通过' if acceptance['heldout_gate_pass'] else '未通过'}

逐动作、逐类别、hard-fail 转移和 bootstrap CI 分别见同目录机器可读文件。本门控不代表下游机器人学习实验已经完成。
"""
    (destination / "HELDOUT_RESULT.md").write_text(report, encoding="utf-8")
    files = []
    for path in sorted(destination.iterdir()):
        if path.name == "comparison_manifest.json":
            continue
        files.append(
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    implementation = Path(__file__).resolve()
    manifest = {
        "complete": True,
        "files": files,
        "implementation": {
            "path": str(implementation),
            "sha256": sha256_file(implementation),
        },
    }
    (destination / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path

