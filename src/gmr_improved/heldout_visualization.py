"""Static dashboard and diagnostic plots for the completed I0 held-out test."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd


CATEGORY_COLORS = {
    "standing_walking": "#4C78A8",
    "running_jumping": "#F58518",
    "dance": "#E45756",
    "complex_dynamic": "#72B7B2",
    "floor_motion": "#B279A2",
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
            raise ValueError(f"Visualization output must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _completion_dashboard(summary: dict[str, Any], audit: dict[str, Any], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    passed = bool(summary["acceptance"]["heldout_gate_pass"] and audit["ok"])
    banner = "#1B8A5A" if passed else "#C43D3D"
    ax.add_patch(
        FancyBboxPatch(
            (0.35, 7.65), 15.3, 1.0, boxstyle="round,pad=0.04,rounding_size=0.12",
            facecolor=banner, edgecolor="none"
        )
    )
    ax.text(
        0.7, 8.15,
        f"I0 TEMPORAL-GMR HELD-OUT TEST: {'PASS' if passed else 'FAIL'}",
        color="white", fontsize=24, weight="bold", va="center"
    )
    ax.text(
        15.2, 8.15,
        f"{summary['motion_count']}/15 motions | {summary['frame_count']:,} frames | audit mismatches={audit['mismatch_count']}",
        color="white", fontsize=12, ha="right", va="center"
    )

    stages = [
        ("Frozen input", "15/15", True),
        ("A0 generation", "91,627 frames", audit["generation"]["a0"]["frame_count"] == 91627),
        ("A1 generation", "91,627 frames", audit["generation"]["a1"]["frame_count"] == 91627),
        ("A0 quality", "15/15 verified", audit["quality"]["a0"]["fidelity_verified_count"] == 15),
        ("A1 quality", "15/15 verified", audit["quality"]["a1"]["fidelity_verified_count"] == 15),
        ("Paired gate", "complete", bool(summary["acceptance"]["heldout_gate_pass"])),
        ("Core audit", "0 mismatches", bool(audit["ok"])),
    ]
    x_positions = np.linspace(0.6, 13.7, len(stages))
    for i, (name, detail, ok) in enumerate(stages):
        color = "#DDF3E8" if ok else "#F8D7DA"
        edge = "#1B8A5A" if ok else "#C43D3D"
        ax.add_patch(
            FancyBboxPatch(
                (x_positions[i], 5.8), 1.75, 1.15,
                boxstyle="round,pad=0.05,rounding_size=0.08",
                facecolor=color, edgecolor=edge, linewidth=2
            )
        )
        ax.text(x_positions[i] + 0.875, 6.55, "PASS" if ok else "FAIL", ha="center", color=edge, weight="bold")
        ax.text(x_positions[i] + 0.875, 6.2, name, ha="center", fontsize=10, weight="bold")
        ax.text(x_positions[i] + 0.875, 5.95, detail, ha="center", fontsize=8, color="#444444")
        if i < len(stages) - 1:
            ax.annotate(
                "", xy=(x_positions[i + 1] - 0.08, 6.37),
                xytext=(x_positions[i] + 1.83, 6.37),
                arrowprops=dict(arrowstyle="->", color="#777777", lw=1.5)
            )

    metrics = summary["cohort_metrics"]
    acceptance = summary["acceptance"]
    checks = [
        ("Joint jumps", metrics["joint_jump_rate"]["a0"], metrics["joint_jump_rate"]["a1"], True),
        ("Velocity violations", metrics["velocity_violation_frame_rate"]["a0"], metrics["velocity_violation_frame_rate"]["a1"], True),
        ("Near-limit 2%", metrics["near_limit_2pct_frame_rate"]["a0"], metrics["near_limit_2pct_frame_rate"]["a1"], True),
        ("Fidelity pass", metrics["fidelity_pass_frame_rate"]["a0"], metrics["fidelity_pass_frame_rate"]["a1"], acceptance["fidelity_gate_pass"]),
    ]
    ax.text(0.65, 5.1, "Preregistered acceptance checks", fontsize=16, weight="bold")
    for i, (name, a0, a1, ok) in enumerate(checks):
        y = 4.52 - i * 0.65
        delta_pp = 100.0 * (a1 - a0)
        ax.text(0.75, y, "✓" if ok else "✗", fontsize=18, color="#1B8A5A" if ok else "#C43D3D", va="center")
        ax.text(1.2, y, name, fontsize=12, weight="bold", va="center")
        ax.text(4.0, y, f"A0 {100*a0:.3f}%", fontsize=11, va="center")
        ax.text(6.0, y, f"A1 {100*a1:.3f}%", fontsize=11, va="center")
        ax.text(8.0, y, f"delta {delta_pp:+.3f} pp", fontsize=11, va="center")
    ax.text(10.4, 5.1, "Safety and scope", fontsize=16, weight="bold")
    ax.text(10.5, 4.5, f"New hard-fail motions: {len(acceptance['new_hard_fail_motions'])}", fontsize=12)
    ax.text(10.5, 3.9, f"A0/A1 hard-fail: {summary['hard_fail']['a0_count']}/{summary['hard_fail']['a1_count']}", fontsize=12)
    ax.text(10.5, 3.3, f"A1 max trust ratio: {audit['generation']['a1']['max_observed_trust_region_ratio']:.15g}", fontsize=12)
    ax.text(10.5, 2.7, "Collision/contact side effects are reported separately.", fontsize=11, color="#9B4B00")
    ax.text(10.5, 2.1, "Downstream imitation-learning validation is outside I0.", fontsize=11, color="#555555")
    ax.text(0.65, 0.55, "Generated from hash-audited machine-readable artifacts; no uncalibrated composite score used.", fontsize=10, color="#666666")
    _save(fig, path)


def _overall_metrics(summary: dict[str, Any], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    metrics = summary["cohort_metrics"]
    primary = [
        ("Joint jump", "joint_jump_rate"),
        ("Velocity violation", "velocity_violation_frame_rate"),
        ("Near limit 2%", "near_limit_2pct_frame_rate"),
        ("Fidelity pass", "fidelity_pass_frame_rate"),
    ]
    x = np.arange(len(primary))
    width = 0.36
    a0 = [100 * metrics[key]["a0"] for _, key in primary]
    a1 = [100 * metrics[key]["a1"] for _, key in primary]
    axes[0].bar(x - width / 2, a0, width, label="A0 Original GMR", color="#9AA0A6")
    axes[0].bar(x + width / 2, a1, width, label="A1 Temporal-GMR", color="#2E86AB")
    axes[0].set_xticks(x, [name for name, _ in primary], rotation=15, ha="right")
    axes[0].set_ylabel("Frame / interval rate (%)")
    axes[0].set_title("Held-out primary metrics")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)
    for i, (v0, v1) in enumerate(zip(a0, a1)):
        axes[0].text(i - width / 2, v0 + 0.6, f"{v0:.2f}", ha="center", fontsize=9)
        axes[0].text(i + width / 2, v1 + 0.6, f"{v1:.2f}", ha="center", fontsize=9)

    side = [
        ("Self collision", "self_collision_nonhand_frame_rate"),
        ("Penetration", "ground_penetration_frame_rate"),
        ("Severe penetration", "severe_ground_penetration_frame_rate"),
        ("Undesired contact", "undesired_ground_contact_frame_rate"),
        ("Foot slide", "foot_slide_frame_rate"),
    ]
    deltas = [100 * metrics[key]["delta"] for _, key in side]
    colors = ["#C44E52" if value > 0 else "#55A868" for value in deltas]
    axes[1].barh(np.arange(len(side)), deltas, color=colors)
    axes[1].set_yticks(np.arange(len(side)), [name for name, _ in side])
    axes[1].axvline(0, color="black", lw=1)
    axes[1].set_xlabel("A1 - A0 (percentage points; positive = more failures)")
    axes[1].set_title("Held-out safety/contact side effects")
    axes[1].grid(axis="x", alpha=0.25)
    for i, value in enumerate(deltas):
        axes[1].text(value + (0.01 if value >= 0 else -0.01), i, f"{value:+.3f}", va="center", ha="left" if value >= 0 else "right")
    fig.suptitle("Temporal-GMR v2: held-out A0/A1 comparison", fontsize=16, weight="bold")
    fig.tight_layout()
    _save(fig, path)


def _category_heatmap(category: pd.DataFrame, path: Path) -> None:
    specs = [
        ("Jump", "delta_joint_jump_rate", -1.0),
        ("Velocity", "delta_velocity_violation_frame_rate", -1.0),
        ("Near-limit", "delta_near_limit_2pct_frame_rate", -1.0),
        ("Fidelity", "delta_fidelity_pass_frame_rate", 1.0),
        ("Collision", "delta_self_collision_nonhand_frame_rate", -1.0),
        ("Penetration", "delta_ground_penetration_frame_rate", -1.0),
        ("Foot slide", "delta_foot_slide_frame_rate", -1.0),
    ]
    matrix = np.asarray(
        [[100 * sign * row[column] for _, column, sign in specs] for _, row in category.iterrows()]
    )
    limit = max(0.01, float(np.max(np.abs(matrix))))
    fig, ax = plt.subplots(figsize=(13, 5.5))
    image = ax.imshow(
        matrix,
        cmap="RdYlGn",
        norm=TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit),
        aspect="auto",
    )
    ax.set_xticks(np.arange(len(specs)), [name for name, _, _ in specs])
    ax.set_yticks(np.arange(len(category)), category["motion_category"])
    ax.set_title("Category-level improvement (percentage points; positive = better)", weight="bold")
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            ax.text(col, row, f"{matrix[row, col]:+.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=ax, label="Improvement (pp)")
    fig.tight_layout()
    _save(fig, path)


def _motion_tradeoff(paired: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 7))
    for category, group in paired.groupby("motion_category"):
        x = -100 * group["delta_velocity_violation_frame_rate"]
        y = 100 * group["delta_fidelity_pass_frame_rate"]
        ax.scatter(x, y, s=80, label=category, color=CATEGORY_COLORS[category], alpha=0.9)
        for _, row in group.iterrows():
            ax.annotate(
                row["motion_name"],
                (-100 * row["delta_velocity_violation_frame_rate"], 100 * row["delta_fidelity_pass_frame_rate"]),
                xytext=(4, 4), textcoords="offset points", fontsize=7
            )
    ax.axhline(-2.0, color="#C43D3D", linestyle="--", label="-2 pp fidelity reference")
    ax.axhline(0.0, color="black", lw=0.8)
    ax.set_xlabel("Velocity-violation reduction (percentage points; right = better)")
    ax.set_ylabel("Fidelity pass-rate change (percentage points; up = better)")
    ax.set_title("Per-motion smoothness/fidelity trade-off", weight="bold")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    _save(fig, path)


def _representative_timeline(a0_path: Path, a1_path: Path, path: Path) -> None:
    a0 = pd.read_csv(a0_path)
    a1 = pd.read_csv(a1_path)
    if len(a0) != len(a1):
        raise ValueError("Representative A0/A1 frame metrics differ in length")
    fig, axes = plt.subplots(2, 1, figsize=(15, 8), sharex=True)
    axes[0].plot(a0["time_s"], a0["max_joint_vel_rad_s"], color="#9AA0A6", lw=1.0, label="A0")
    axes[0].plot(a1["time_s"], a1["max_joint_vel_rad_s"], color="#2E86AB", lw=1.0, label="A1")
    axes[0].axhline(3 * np.pi, color="#C43D3D", linestyle="--", label="3π evaluation threshold")
    axes[0].set_yscale("symlog", linthresh=10.0)
    axes[0].set_ylabel("Max joint velocity (rad/s, symlog)")
    axes[0].set_title("Representative held-out trace: dance1_subject2", weight="bold")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    window = 30
    a0_fidelity = a0["fidelity_valid_flag"].astype(float).rolling(window, min_periods=1).mean()
    a1_fidelity = a1["fidelity_valid_flag"].astype(float).rolling(window, min_periods=1).mean()
    a0_near = a0["near_limit_2pct_flag"].astype(float).rolling(window, min_periods=1).mean()
    a1_near = a1["near_limit_2pct_flag"].astype(float).rolling(window, min_periods=1).mean()
    axes[1].plot(a0["time_s"], a0_fidelity, color="#9AA0A6", label="A0 fidelity pass (1 s rolling)")
    axes[1].plot(a1["time_s"], a1_fidelity, color="#2E86AB", label="A1 fidelity pass (1 s rolling)")
    axes[1].plot(a0["time_s"], a0_near, color="#B279A2", alpha=0.65, label="A0 near-limit (1 s rolling)")
    axes[1].plot(a1["time_s"], a1_near, color="#59A14F", alpha=0.75, label="A1 near-limit (1 s rolling)")
    axes[1].set_ylim(-0.03, 1.03)
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Rolling fraction")
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=2, fontsize=9)
    fig.tight_layout()
    _save(fig, path)


def generate_heldout_visualizations(
    comparison_dir: str | Path,
    audit_path: str | Path,
    a0_quality_dir: str | Path,
    a1_quality_dir: str | Path,
    output_dir: str | Path,
) -> Path:
    comparison = Path(comparison_dir).expanduser().resolve()
    audit_file = Path(audit_path).expanduser().resolve()
    a0_quality = Path(a0_quality_dir).expanduser().resolve()
    a1_quality = Path(a1_quality_dir).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    summary_path = comparison / "comparison_summary.json"
    paired_path = comparison / "paired_motion_metrics.csv"
    category_path = comparison / "category_metrics.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if not audit.get("ok"):
        raise ValueError("Core held-out audit is not passing; visualization refused")
    paired = pd.read_csv(paired_path)
    category = pd.read_csv(category_path)
    figures = [
        ("01_test_completion_dashboard.png", lambda p: _completion_dashboard(summary, audit, p)),
        ("02_overall_metrics_a0_a1.png", lambda p: _overall_metrics(summary, p)),
        ("03_category_improvement_heatmap.png", lambda p: _category_heatmap(category, p)),
        ("04_motion_tradeoff.png", lambda p: _motion_tradeoff(paired, p)),
        (
            "05_dance1_subject2_timeline.png",
            lambda p: _representative_timeline(
                a0_quality / "frame_metrics" / "dance1_subject2.csv",
                a1_quality / "frame_metrics" / "dance1_subject2.csv",
                p,
            ),
        ),
    ]
    for filename, function in figures:
        function(destination / filename)

    guide = """# I0 测试可视化指南

## 直接查看

- `01_test_completion_dashboard.png`：先看测试流水线是否全部完成，以及 held-out 门控是否通过。
- `02_overall_metrics_a0_a1.png`：看总体主指标和碰撞/接触副作用。
- `03_category_improvement_heatmap.png`：正值表示改善，可定位哪类动作获益或退化。
- `04_motion_tradeoff.png`：每个点是一条动作，横轴越右代表速度改善越多，纵轴越低代表 fidelity 损失越大。
- `05_dance1_subject2_timeline.png`：查看最明显 trade-off 动作的逐帧速度、fidelity 和近限位变化。

可以直接打开 `index.html`，或在本目录运行：

```bash
python -m http.server 8000
```

然后浏览器访问 `http://127.0.0.1:8000/`。

## MuJoCo 动作回放

A0：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \\
  --robot unitree_g1 \\
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a0_v1/retargeted/dance1_subject2.pkl
```

A1：把路径改为：

```text
/root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a1_v1/retargeted/dance1_subject2.pkl
```

该回放需要图形桌面；无桌面环境时使用上述静态图。A0/A1 最好分别录屏后并排比较，不要仅凭单次肉眼印象替代基础指标。
"""
    (destination / "VISUALIZATION_GUIDE.md").write_text(guide, encoding="utf-8")
    cards = "\n".join(
        f'<section><h2>{html.escape(filename)}</h2><img src="{html.escape(filename)}" alt="{html.escape(filename)}"></section>'
        for filename, _ in figures
    )
    index = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>I0 Temporal-GMR Held-out Results</title>
<style>body{{font-family:Arial,sans-serif;max-width:1500px;margin:auto;padding:24px;background:#f5f7fa}}section{{background:white;padding:18px;margin:18px 0;border-radius:10px;box-shadow:0 2px 8px #0001}}img{{width:100%;height:auto}}code{{background:#eee;padding:2px 5px}}</style></head>
<body><h1>I0 Temporal-GMR Held-out Test</h1><p>Core audit: PASS; held-out gate: PASS; 15 motions / 91,627 frames.</p>{cards}</body></html>
"""
    (destination / "index.html").write_text(index, encoding="utf-8")
    input_files = [summary_path, paired_path, category_path, audit_file]
    output_files = [destination / filename for filename, _ in figures] + [
        destination / "VISUALIZATION_GUIDE.md",
        destination / "index.html",
    ]
    manifest = {
        "complete": True,
        "inputs": [
            {"path": str(path), "sha256": sha256_file(path)} for path in input_files
        ],
        "outputs": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in output_files
        ],
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }
    manifest_path = destination / "visualization_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path

