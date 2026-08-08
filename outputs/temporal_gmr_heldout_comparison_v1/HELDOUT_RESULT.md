# Temporal-GMR v2 预注册独立测试

同一组 15 条、91,627 帧 held-out 动作的 A0/A1 配对比较。该队列在开发结果前已写入 `PLAN.md`；未使用未校准 `quality_score`。

| 指标 | A0 | A1 | A1-A0 |
|---|---:|---:|---:|
| `joint_jump_rate` | 0.0164279789 | 0 | -0.0164279789 |
| `velocity_violation_frame_rate` | 0.113696896 | 0 | -0.113696896 |
| `near_limit_2pct_frame_rate` | 0.579261571 | 0.561417486 | -0.0178440853 |
| `fidelity_pass_frame_rate` | 0.901993954 | 0.887533151 | -0.014460803 |

- A0/A1 hard-fail：12/12
- 新增 hard-fail：无
- fidelity pass rate 下降：0.014460803（上限 0.02）
- held-out 门控：通过

逐动作、逐类别、hard-fail 转移和 bootstrap CI 分别见同目录机器可读文件。本门控不代表下游机器人学习实验已经完成。
