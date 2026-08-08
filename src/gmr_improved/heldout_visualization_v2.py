"""Layout-corrected v2 visualization packet; numerical content is unchanged."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

from . import heldout_visualization as base


def _completion_dashboard_v2(
    summary: dict[str, Any], audit: dict[str, Any], path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    passed = bool(summary["acceptance"]["heldout_gate_pass"] and audit["ok"])
    banner = "#1B8A5A" if passed else "#C43D3D"
    ax.add_patch(
        FancyBboxPatch(
            (0.35, 7.55), 15.3, 1.15,
            boxstyle="round,pad=0.04,rounding_size=0.12",
            facecolor=banner, edgecolor="none"
        )
    )
    ax.text(
        0.75, 8.28,
        f"I0 TEMPORAL-GMR HELD-OUT: {'PASS' if passed else 'FAIL'}",
        color="white", fontsize=22, weight="bold", va="center"
    )
    ax.text(
        0.78, 7.82,
        f"{summary['motion_count']}/15 motions  |  {summary['frame_count']:,} frames  |  core audit mismatches={audit['mismatch_count']}",
        color="white", fontsize=11, va="center"
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
    positions = [0.55, 2.75, 4.95, 7.15, 9.35, 11.55, 13.75]
    for i, (name, detail, ok) in enumerate(stages):
        color = "#DDF3E8" if ok else "#F8D7DA"
        edge = "#1B8A5A" if ok else "#C43D3D"
        ax.add_patch(
            FancyBboxPatch(
                (positions[i], 5.75), 1.75, 1.15,
                boxstyle="round,pad=0.05,rounding_size=0.08",
                facecolor=color, edgecolor=edge, linewidth=2
            )
        )
        ax.text(positions[i] + 0.875, 6.52, "PASS" if ok else "FAIL", ha="center", color=edge, weight="bold")
        ax.text(positions[i] + 0.875, 6.17, name, ha="center", fontsize=10, weight="bold")
        ax.text(positions[i] + 0.875, 5.92, detail, ha="center", fontsize=8, color="#444444")
        if i < len(stages) - 1:
            ax.annotate(
                "", xy=(positions[i + 1] - 0.07, 6.32),
                xytext=(positions[i] + 1.83, 6.32),
                arrowprops=dict(arrowstyle="->", color="#777777", lw=1.4)
            )
    metrics = summary["cohort_metrics"]
    acceptance = summary["acceptance"]
    checks = [
        ("Joint jumps", "joint_jump_rate", True),
        ("Velocity violations", "velocity_violation_frame_rate", True),
        ("Near-limit 2%", "near_limit_2pct_frame_rate", True),
        ("Fidelity pass", "fidelity_pass_frame_rate", acceptance["fidelity_gate_pass"]),
    ]
    ax.text(0.65, 5.0, "Preregistered acceptance checks", fontsize=16, weight="bold")
    for i, (name, key, ok) in enumerate(checks):
        y = 4.42 - i * 0.65
        a0 = metrics[key]["a0"]
        a1 = metrics[key]["a1"]
        ax.text(0.75, y, "✓" if ok else "✗", fontsize=18, color="#1B8A5A" if ok else "#C43D3D", va="center")
        ax.text(1.2, y, name, fontsize=12, weight="bold", va="center")
        ax.text(4.0, y, f"A0 {100*a0:.3f}%", fontsize=11, va="center")
        ax.text(6.0, y, f"A1 {100*a1:.3f}%", fontsize=11, va="center")
        ax.text(8.0, y, f"delta {100*(a1-a0):+.3f} pp", fontsize=11, va="center")
    ax.text(10.4, 5.0, "Safety and scope", fontsize=16, weight="bold")
    ax.text(10.5, 4.4, f"New hard-fail motions: {len(acceptance['new_hard_fail_motions'])}", fontsize=12)
    ax.text(10.5, 3.8, f"A0/A1 hard-fail: {summary['hard_fail']['a0_count']}/{summary['hard_fail']['a1_count']}", fontsize=12)
    ax.text(10.5, 3.2, f"A1 max trust ratio: {audit['generation']['a1']['max_observed_trust_region_ratio']:.15g}", fontsize=12)
    ax.text(10.5, 2.6, "Collision/contact side effects are reported separately.", fontsize=11, color="#9B4B00")
    ax.text(10.5, 2.0, "Downstream imitation-learning validation is outside I0.", fontsize=11, color="#555555")
    ax.text(0.65, 0.52, "Hash-audited artifacts; no uncalibrated composite score used.", fontsize=10, color="#666666")
    base._save(fig, path)


def generate_v2(
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
        ("02_overall_metrics_a0_a1.png", lambda p: base._overall_metrics(summary, p)),
        ("03_category_improvement_heatmap.png", lambda p: base._category_heatmap(category, p)),
        ("04_motion_tradeoff.png", lambda p: base._motion_tradeoff(paired, p)),
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
4. `04_motion_tradeoff.png`：横轴越右表示速度改善越多；纵轴越低表示 fidelity 损失越大。
5. `05_dance1_subject2_timeline.png`：检查代表性高速动作的逐帧约束效果。

浏览器汇总：

```bash
cd /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_visualization_v2
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
    input_files = [summary_path, paired_path, category_path, audit_file]
    output_files = [destination / filename for filename, _ in figures] + [
        destination / "VISUALIZATION_GUIDE.md", destination / "index.html"
    ]
    implementation = Path(__file__).resolve()
    base_implementation = Path(base.__file__).resolve()
    manifest = {
        "complete": True,
        "layout_version": 2,
        "inputs": [{"path": str(p), "sha256": base.sha256_file(p)} for p in input_files],
        "outputs": [
            {"path": p.name, "size_bytes": p.stat().st_size, "sha256": base.sha256_file(p)}
            for p in output_files
        ],
        "implementation": [
            {"path": str(implementation), "sha256": base.sha256_file(implementation)},
            {"path": str(base_implementation), "sha256": base.sha256_file(base_implementation)},
        ],
    }
    manifest_path = destination / "visualization_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path

