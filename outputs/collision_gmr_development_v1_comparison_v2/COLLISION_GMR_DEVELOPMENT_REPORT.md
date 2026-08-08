# Collision-GMR 冻结开发集配对结果

本报告比较同一组 15 条、90,540 帧 LAFAN1 动作的 A1 Temporal-GMR v2 与 A2 Collision-GMR v1。所有基础指标独立报告，未使用未校准 `quality_score`。

| 指标 | A1 | A2 | A2-A1 |
|---|---:|---:|---:|
| `self_collision_nonhand_frame_rate` | 0.0243538767 | 0.0181466755 | -0.00620720124 |
| `self_collision_nonhand_event_count` | 572 | 563 | -9 |
| `joint_jump_rate` | 0 | 0 | 0 |
| `velocity_violation_frame_rate` | 0 | 0 | 0 |
| `fidelity_pass_frame_rate` | 0.865286061 | 0.864976806 | -0.000309255578 |

- 新增 hard-fail 动作：无
- fidelity pass rate 下降：0.000309255578（门限 0.02）
- 开发门控：通过

该门控只检验冻结开发集上的预注册工程标准；不代表独立留出集或机器人学习效果。完整总体指标、bootstrap 区间见 `comparison_summary.json`，逐动作和逐类别结果分别见 `paired_motion_metrics.csv` 与 `category_metrics.csv`。
