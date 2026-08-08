# Contact-GMR development 配对结果

本报告比较 A2 Collision-GMR 与 A3 Contact-GMR，共 15 条、90,540 帧；主要接触门控只在 `feet_only` 队列计算，`floor_motion` 要求逐元素 no-op。未使用未校准综合分数。

| feet_only 指标 | A2 | A3 | A3-A2 |
|---|---:|---:|---:|
| `foot_slide_frame_rate` | 0.0215355435 | 0.0157795603 | -0.00575598319 |
| `ground_penetration_frame_rate` | 0.0259611965 | 0.00352998512 | -0.0224312114 |
| `severe_ground_penetration_frame_rate` | 0.00561109574 | 0.0017254778 | -0.00388561794 |
| `undesired_ground_contact_frame_rate` | 0.0113934221 | 0.00886447755 | -0.00252894456 |

- 新增 hard-fail：无
- 总体 fidelity pass rate 下降：0.0212171416
- 总体非手部碰撞帧率增加：0.000596421471
- Contact 门控：未通过

逐动作和分 policy 结果见同目录 CSV；门控通过也不代表动力学执行或下游学习已经验证。
