# Contact-GMR development 配对结果

本报告比较 A2 Collision-GMR 与 A3 Contact-GMR，共 15 条、90,540 帧；主要接触门控只在 `feet_only` 队列计算，`floor_motion` 要求逐元素 no-op。未使用未校准综合分数。

| feet_only 指标 | A2 | A3 | A3-A2 |
|---|---:|---:|---:|
| `foot_slide_frame_rate` | 0.0215355435 | 0.0177026119 | -0.0038329316 |
| `ground_penetration_frame_rate` | 0.0259611965 | 0.00363535781 | -0.0223258387 |
| `severe_ground_penetration_frame_rate` | 0.00561109574 | 0.00179133573 | -0.00381976001 |
| `undesired_ground_contact_frame_rate` | 0.0113934221 | 0.00887764914 | -0.00251577297 |

- 新增 hard-fail：无
- 总体 fidelity pass rate 下降：0.00250717915
- 总体非手部碰撞帧率增加：-0.000684780208
- Contact 门控：通过

逐动作和分 policy 结果见同目录 CSV；门控通过也不代表动力学执行或下游学习已经验证。
