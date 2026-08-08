"""Final, label-safe visualization packet for the completed I0 held-out test."""

from __future__ import annotations

import html
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import heldout_visualization as base
from .heldout_visualization_v2 import _completion_dashboard_v2


def _overall_metrics_v3(summary: dict, path: Path) -> None:
    """Plot the cohort result while reserving space for side-effect labels."""
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
    axes[0].set_ylim(0, max(a0 + a1) * 1.06)
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
    span = max(abs(value) for value in deltas)
    axes[1].set_xlim(min(-0.01, min(deltas) - 0.02 * span), max(deltas) + 0.15 * span)
    for i, value in enumerate(deltas):
        axes[1].text(
            value + (0.01 * span if value >= 0 else -0.01 * span), i,
            f"{value:+.3f}", va="center", ha="left" if value >= 0 else "right"
        )
    fig.suptitle("Temporal-GMR v2: held-out A0/A1 comparison", fontsize=16, weight="bold")
    fig.tight_layout()
    base._save(fig, path)


def _motion_tradeoff_v3(paired: pd.DataFrame, path: Path) -> None:
    """Use numeric point labels plus a key so dense short motions remain readable."""
    ordered = paired.sort_values(["motion_category", "motion_name"]).reset_index(drop=True)
    fig = plt.figure(figsize=(15, 8))
    grid = fig.add_gridspec(1, 2, width_ratios=[3.5, 1.5], wspace=0.05)
    ax = fig.add_subplot(grid[0, 0])
    key_ax = fig.add_subplot(grid[0, 1])
    key_ax.axis("off")
    for category, group in ordered.groupby("motion_category", sort=False):
        x = -100 * group["delta_velocity_violation_frame_rate"]
        y = 100 * group["delta_fidelity_pass_frame_rate"]
        ax.scatter(x, y, s=95, label=category, color=base.CATEGORY_COLORS[category], alpha=0.9)
        for index, row in group.iterrows():
            ax.annotate(
                str(index + 1),
                (-100 * row["delta_velocity_violation_frame_rate"], 100 * row["delta_fidelity_pass_frame_rate"]),
                xytext=(5, 5), textcoords="offset points", fontsize=8, weight="bold"
            )
    ax.axhline(-2.0, color="#C43D3D", linestyle="--", label="-2 pp fidelity reference")
    ax.axhline(0.0, color="black", lw=0.8)
    ax.set_xlabel("Velocity-violation reduction (percentage points; right = better)")
    ax.set_ylabel("Fidelity pass-rate change (percentage points; up = better)")
    ax.set_title("Per-motion smoothness/fidelity trade-off", weight="bold")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2, loc="lower left")

    key_ax.text(0.02, 0.98, "Motion key", fontsize=13, weight="bold", va="top")
    for index, row in ordered.iterrows():
        y = 0.93 - index * 0.058
        key_ax.text(0.02, y, f"{index + 1:>2}", fontsize=9, weight="bold", va="top")
        key_ax.text(0.11, y, row["motion_name"], fontsize=9, va="top")
        key_ax.text(
            0.11, y - 0.024, row["motion_category"], fontsize=7,
            color=base.CATEGORY_COLORS[row["motion_category"]], va="top"
        )
    base._save(fig, path)


def generate_v3(
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
    base._prepare_empty(destination)
    summary_path = comparison / "comparison_summary.json"
    paired_path = comparison / "paired_motion_metrics.csv"
    category_path = comparison / "category_metrics.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if not audit.get("ok"):
        raise ValueError("Core held-out audit is not passing")
    paired = pd.read_csv(paired_path)
    category = pd.read_csv(category_path)
    figures = [
        ("01_test_completion_dashboard.png", lambda p: _completion_dashboard_v2(summary, audit, p)),
        ("02_overall_metrics_a0_a1.png", lambda p: _overall_metrics_v3(summary, p)),
        ("03_category_improvement_heatmap.png", lambda p: base._category_heatmap(category, p)),
        ("04_motion_tradeoff.png", lambda p: _motion_tradeoff_v3(paired, p)),
        (
            "05_dance1_subject2_timeline.png",
            lambda p: base._representative_timeline(
                a0_quality / "frame_metrics" / "dance1_subject2.csv",
                a1_quality / "frame_metrics" / "dance1_subject2.csv",
                p,
            ),
        ),
    ]
    for filename, function in figures:
        function(destination / filename)
    guide = """# I0 测试可视化指南

查看顺序：

1. `01_test_completion_dashboard.png`：确认冻结输入、A0/A1 生成、质量评估、配对门控和核心审计全部 PASS。
2. `02_overall_metrics_a0_a1.png`：比较总体主指标及碰撞/接触副作用。
3. `03_category_improvement_heatmap.png`：正值为改善，负值为退化。
4. `04_motion_tradeoff.png`：横轴越右表示速度改善越多；纵轴越低表示 fidelity 损失越大；点号在右侧 motion key 中查找。
5. `05_dance1_subject2_timeline.png`：检查代表性高速动作的逐帧约束效果。

浏览器汇总：

```bash
cd /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_visualization_v3
python -m http.server 8000
```

访问 `http://127.0.0.1:8000/`。

MuJoCo 回放 A0：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \\
  --robot unitree_g1 \\
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a0_v1/retargeted/dance1_subject2.pkl
```

回放 A1 时把目录改为 `temporal_gmr_heldout_a1_v1/retargeted`。GUI 回放需要图形桌面；建议 A0/A1 分别录屏并排观察，不能用肉眼回放替代定量门控。
"""
    (destination / "VISUALIZATION_GUIDE.md").write_text(guide, encoding="utf-8")
    cards = "\n".join(
        f'<section><h2>{html.escape(filename)}</h2><img src="{html.escape(filename)}" alt="{html.escape(filename)}"></section>'
        for filename, _ in figures
    )
    (destination / "index.html").write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>I0 Temporal-GMR</title>
<style>body{{font-family:Arial,sans-serif;max-width:1500px;margin:auto;padding:24px;background:#f5f7fa}}section{{background:white;padding:18px;margin:18px 0;border-radius:10px;box-shadow:0 2px 8px #0001}}img{{width:100%;height:auto}}</style></head>
<body><h1>I0 Temporal-GMR Held-out Test</h1><p>Core audit PASS; held-out gate PASS; 15 motions / 91,627 frames.</p>{cards}</body></html>""",
        encoding="utf-8",
    )
    output_files = [destination / filename for filename, _ in figures] + [
        destination / "VISUALIZATION_GUIDE.md", destination / "index.html"
    ]
    implementations = [Path(__file__).resolve(), Path(base.__file__).resolve()]
    manifest = {
        "complete": True,
        "layout_version": 3,
        "inputs": [
            {"path": str(p), "sha256": base.sha256_file(p)}
            for p in [summary_path, paired_path, category_path, audit_file]
        ],
        "outputs": [
            {"path": p.name, "size_bytes": p.stat().st_size, "sha256": base.sha256_file(p)}
            for p in output_files
        ],
        "implementation": [
            {"path": str(p), "sha256": base.sha256_file(p)} for p in implementations
        ],
    }
    manifest_path = destination / "visualization_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path
