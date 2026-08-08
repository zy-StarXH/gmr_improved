# Temporal-GMR 冻结开发集配对结果

本报告比较同一组 15 条、90,540 帧 LAFAN1 动作的 A0 与 A1。所有基础指标保持独立，未使用未校准 `quality_score`。

| 指标 | A0 | A1 | A1-A0 |
|---|---:|---:|---:|
| `joint_jump_rate` | 0.0218724109 | 0 | -0.0218724109 |
| `velocity_violation_frame_rate` | 0.0970229218 | 0.0115990058 | -0.085423916 |
| `near_limit_2pct_frame_rate` | 0.545902364 | 0.530251822 | -0.0156505412 |
| `fidelity_pass_frame_rate` | 0.878793903 | 0.865330241 | -0.0134636625 |

- 新增 hard-fail 动作：无
- fidelity pass rate 下降：0.0134636625（门限 0.02）
- 开发门控：通过

“通过”只表示冻结开发集满足预注册工程门控，不是对冻结正式测试集或下游机器人学习效果的结论。逐动作结果见 `paired_motion_metrics.csv`，配对 motion-level bootstrap 区间和完整指标见 `comparison_summary.json`。
