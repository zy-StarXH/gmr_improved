# Contact-GMR heldout 配对结果

本报告比较 A2 Collision-GMR 与 A3 Contact-GMR，共 15 条、91,627 帧；主要接触门控只在 `feet_only` 队列计算，`floor_motion` 要求逐元素 no-op。未使用未校准综合分数。

| feet_only 指标 | A2 | A3 | A3-A2 |
|---|---:|---:|---:|
| `foot_slide_frame_rate` | 0.0202786196 | 0.0161162346 | -0.00416238505 |
| `ground_penetration_frame_rate` | 0.043418879 | 0.00543711547 | -0.0379817636 |
| `severe_ground_penetration_frame_rate` | 0.00725815893 | 0.00120969315 | -0.00604846577 |
| `undesired_ground_contact_frame_rate` | 0.031998335 | 0.0296700009 | -0.00232833414 |

- 新增 hard-fail：无
- 总体 fidelity pass rate 下降：0.00399445578
- 总体非手部碰撞帧率增加：0.000327414408
- Contact 门控：通过

逐动作和分 policy 结果见同目录 CSV；门控通过也不代表动力学执行或下游学习已经验证。
