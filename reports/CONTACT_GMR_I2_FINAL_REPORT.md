# Contact-GMR I2 最终报告

## 最终结论

Contact-GMR v2 通过冻结开发集和独立 held-out 的预注册门控。相对 A2 Collision-GMR，它在 held-out 的 `feet_only` 队列中同时降低脚滑、穿地、严重穿地和非预期触地，并保持无新增 hard-fail、零突跳/零速度超限、`floor_motion` 逐元素 no-op。未校准综合分数未参与候选选择或结论。

结论严格限定为：该接触约束改善了离线运动学轨迹的接触相关指标。它不等于动力学稳定、仿真任务成功或模仿学习收益已经得到验证。

## 方法与候选选择

A3 直接继承冻结 A2 Collision-GMR v1：

- 人体接触由 LAFAN1 `LeftFootMod/RightFootMod` 的世界高度、竖直速度和水平速度因果推断；双足高度 2% 分位为源地面，进入/退出高度为 `0.04/0.06 m`，速度迟滞为 `0.2/0.4 m/s`。
- 接触脚对 G1 ankle-roll body 添加世界位置 FrameTask；不约束足部姿态。
- MuJoCo 全 body-ground 最大接触深度用于根高度修正，目标残余 `0.005 m`；根上移最大 `0.05 m`，每帧上升/释放最大 `0.02/0.005 m`。
- `floor_motion` 的人体标签、足 anchor、根上移全部关闭，并与 A2 PKL 逐元素比较。

v1 anchor xy/z cost=`100/50`。它在开发集显著改善接触指标，但总体 fidelity 下降 `0.02121714`，略超过冻结上限 `0.02`，因此正式判为失败并保留全部负结果。逐帧归因显示 2,355 个 fidelity 损失帧中 2,335 个发生在 anchor 活跃时，仅 103 个同时发生直接根上移。

v2 在查看其输出前只做一次预注册变化：anchor xy/z cost 同比例减半为 `50/25`。接触标签、根修正、父方法、数据、评价器和验收门槛均不变。v2 开发门控通过后才解封 I0 前已冻结的 15 条 held-out 动作。

## 开发集结果

开发集包含 15 条、90,540 帧，其中 12 条 `feet_only`、3 条 `floor_motion`。

| `feet_only` 指标 | A2 | A3 v2 | A3-A2 |
|---|---:|---:|---:|
| 脚滑帧率 | 0.02153554 | 0.01770261 | -0.00383293 |
| 穿地帧率 | 0.02596120 | 0.00363536 | -0.02232584 |
| 严重穿地帧率 | 0.00561110 | 0.00179134 | -0.00381976 |
| 非预期触地帧率 | 0.01139342 | 0.00887765 | -0.00251577 |

总体 fidelity pass rate `0.86497681 -> 0.86246963`，下降 `0.00250718`；非手部自碰撞帧率下降 `0.00068478`；hard-fail `12 -> 10` 且无新增。开发 `contact_gate_pass=true`。

## 独立 held-out 结果

held-out 为事先冻结且与开发 motion name 不相交的 15 条、91,627 帧；12 条 `feet_only` 共 76,879 帧。

| `feet_only` 指标 | A2 | A3 v2 | A3-A2 |
|---|---:|---:|---:|
| 脚滑帧率 | 0.02027862 | 0.01611623 | -0.00416239 |
| 脚滑帧数 / 事件数 | 1,559 / 1,001 | 1,239 / 749 | -320 / -252 |
| 穿地帧率 | 0.04341888 | 0.00543712 | -0.03798176 |
| 穿地帧数 / 事件数 | 3,338 / 264 | 418 / 39 | -2,920 / -225 |
| 严重穿地帧率 | 0.00725816 | 0.00120969 | -0.00604847 |
| 严重穿地帧数 | 558 | 93 | -465 |
| 非预期触地帧率 | 0.03199834 | 0.02967000 | -0.00232833 |
| 非预期触地帧数 / 事件数 | 2,460 / 304 | 2,281 / 181 | -179 / -123 |

motion-level bootstrap 使用固定 seed、10,000 次重采样：

- 脚滑帧率平均配对差 95% CI：`[-0.006544, -0.001382]`；
- 穿地帧率：`[-0.078298, -0.010643]`；
- 严重穿地：`[-0.014553, -0.000490]`；
- 非预期触地：`[-0.004064, -0.000886]`。

四项区间均完全小于 0，支持改善不只由单条动作驱动。

保持门控结果：

- 总体 fidelity pass rate `0.88739127 -> 0.88339682`，下降 `0.00399446 < 0.02`；
- 总体非手部自碰撞帧率 `0.01467908 -> 0.01500649`，增加 `0.00032741 < 0.001`；
- hard-fail `12 -> 11`，无新增，`jumps1_subject1` 从 hard-fail 变为非 hard-fail；
- 突跳率与速度超限率均保持 0；
- 3 条 `floor_motion` 的 `root_pos/root_rot/dof_pos` 最大绝对差均严格为 0。

held-out `contact_gate_pass=true`。

## 逐帧 intervention 审计

独立 held-out 审计重新检查文件/源码哈希、连续 frame index、source/runtime 接触标签、transition、anchor 数量、root lift 幅度与上升/释放速度、root/sole 位移一致性、穿透非增加性和 floor no-op：0 integrity mismatch、0 Contact invariant failure。

12 条 `feet_only` 中：

- 人体接触 53,645 帧，anchor 活跃 53,633 帧；12 帧差异来自首帧必须先对齐再建立 anchor。
- 根高度修正 4,290 帧，clipped 1,173 帧，最大上移 5 cm。
- 修正前最大穿透 `0.12078 m`，修正后最大仍为 `0.07078 m`。因此不能声称完全消除穿透。
- 最大左右 anchor error 分别为 `0.21653/0.18812 m`，说明软约束允许在冲突姿态中牺牲足底保持；这正是 v2 用于控制 fidelity 代价的机制之一。

## 必须保留的副作用与反例

- 总体 root jerk p95 `404.64 -> 429.33 m/s^3`，joint jerk p95 `3000.74 -> 3024.62 rad/s³`；12 条 `feet_only` 的 root jerk p95 均增加。Contact v2 改善接触，但没有改善时序平滑性。
- 非手部自碰撞事件数 `488 -> 501`，虽然帧率增加未越过门控上限；接触任务可能改变碰撞事件碎片化。
- `walk3_subject3` 穿地帧率大幅下降 `0.25206`，但自碰撞帧率增加 `0.00460`、root jerk p95 增加 `143.89 m/s³`，且 2,159 帧触发根修正。这是最重要的接触收益/时序与碰撞代价反例。
- `dance1_subject2` 的脚滑帧率增加 `0.00330`，同时自碰撞帧率增加 `0.00279`；总体门控通过不表示每条动作单调改善。
- `multipleActions1_subject2` fidelity 下降 `0.01744`，仍在总体允许范围内，但接近单动作明显退化。
- 右脚 contact-proxy mismatch 帧率增加约 `0.00151`，说明源人体接触标签、MuJoCo 接触和冻结脚底代理并不完全等价。

## 如何可视化复核

项目已生成不覆盖冻结 PKL 的 viewer 兼容副本。先看 `walk3_subject3` 的 A2：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/visualization_compat/walk3_subject3_a2_collision_v1.pkl
```

再看 A3 Contact v2：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/visualization_compat/walk3_subject3_a3_contact_v2.pkl
```

建议重点观察足底/地面的相对高度、根部上下运动是否呈阶梯或抖动，以及躯干/腿部自碰撞。再用同样方式比较 `dance1_subject2_a2_collision_for_contact.pkl` 与 `dance1_subject2_a3_contact_v2.pkl`，检查脚滑恶化反例。

MuJoCo 回放只验证运动学外观；viewer 到末帧会直接回到首帧，循环边界突变不能误判为算法内部突跳。

## 可追溯产物

- v1 负结果：`reports/CONTACT_GMR_V1_DEVELOPMENT_REPORT.md`
- v2 开发配置：`configs/contact_gmr_v2.yaml`
- v2 held-out 配置：`configs/contact_gmr_heldout_v2.yaml`
- 开发生成/质量/比较：`outputs/contact_gmr_development_v2*`
- held-out 生成/质量/比较：`outputs/contact_gmr_heldout_v2*`
- 开发审计：`data/contact_gmr_development_v2_audit.json`
- held-out 审计：`data/contact_gmr_heldout_v2_audit.json`

held-out 核心 SHA-256：生成 manifest `adf11ace...ec56`，质量 manifest `97728ba5...833e`，比较 summary `579875be...49b8`，比较 manifest `730a4f13...c977`，独立审计 `bcee3c1b...ee2e`。

## 后续研究边界

下一步应把 Contact-GMR v2 与 A2 轨迹用于相同的仿真 tracking/任务策略训练，验证离线评分是否预测任务成功率、训练效率和稳定性。同时应新增连续的根/关节 jerk 指标或根部时序正则，并将 `walk3_subject3`、`dance1_subject2` 固定为回归反例；不能继续用 held-out 调 Contact 参数。
