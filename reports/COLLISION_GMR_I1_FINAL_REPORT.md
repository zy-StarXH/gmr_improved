# Collision-GMR I1 最终报告

## 1. 结论

本阶段已实现并冻结 **Collision-GMR v1**：它在 I0 的 Temporal-GMR v2 上加入经过模型等价性验证和 pair 审计的非相邻自碰撞速度约束。候选在开发集和预注册独立留出集上均通过事先定义的工程门控，但结果应准确表述为：

> Collision-GMR v1 能显著减少非手部碰撞持续帧和穿透程度，并在留出集上减少连续碰撞事件；它不是严格的无碰撞投影，仍存在低于 5 mm 余量和负 signed distance 的帧。

独立留出集包含 15 条、91,627 帧。相对冻结 A1，A2 的非手部自碰撞帧率从 `1.9961%` 降至 `1.4679%`（相对减少 `26.46%`），连续事件从 `542` 降至 `488`（减少 `9.96%`）。突跳率和速度超限率保持为 0，无新增 hard-fail；总体 fidelity pass rate 仅下降 `0.0142` 个百分点，小于预注册的 2 个百分点门限。

这不等于课题的机器人学习验证已完成。I1 只验证了运动重定向层面的碰撞改进；模仿学习成功率、训练效率和策略稳定性仍属于后续 I2。

## 2. 审计后模型与 pair

原 G1 XML 中 72 个 geom 有 71 个未命名，无法稳定引用单个碰撞几何。派生模型 [`g1_mocap_29dof_collision_named.xml`](../assets/collision_g1_v1/g1_mocap_29dof_collision_named.xml) 只做两类变换：

1. 为 71 个未命名 geom 加入确定性唯一名称；
2. 把相对 `meshdir` 重定位到原 GMR 的只读资产目录，使派生 XML 可从本项目加载。

等价性门控比较了 `nq/nv/nbody/njnt/ngeom/nsite/nu/nmesh`、模型数值数组和名称；固定 seed 的 16 组 qpos 下，body/geom/site 的 FK 最大绝对误差均为 0，模型 mismatch 为 0。完整机器审计见 [`collision_model_audit.json`](../assets/collision_g1_v1/collision_model_audit.json)。

pair 从机器人树拓扑机械生成，规则在读取 A2 动作输出前冻结：

- 排除 world/floor 和同 body；
- 排除 body 树距离小于 3 的结构近邻；
- 排除质量评价中预注册的允许手部接触 body；
- 排除 MuJoCo `contype/conaffinity` 不相容 geom；
- 保留 193 个 body pair、362 个 geom pair。

中立位没有 pair 低于 5 mm，最近距离为 `7.81156 mm`；Mink 运行时展开的 362 个 pair 与冻结 CSV 逐项一致。清单见 [`collision_pairs.csv`](../assets/collision_g1_v1/collision_pairs.csv)。

## 3. 算法实现

核心实现在 [`collision.py`](../src/gmr_improved/collision.py)：

- 完整继承冻结的 Temporal-GMR v2，不回调其速度信赖域、跨帧 posture 正则或软限位参数；
- 构造 GMR 时临时、线程加锁地把机器人 XML 指向派生模型，构造结束或异常后恢复上游全局映射；
- 加载 pair CSV 时逐行复核 geom ID、名称、body、树距离、手部排除和 pair 总数；
- 用确定性 pair 顺序构造 Mink `CollisionAvoidanceLimit`，并追加到同一个 IK QP 的 limits；
- 每帧独立记录 broadphase 候选、激活 pair、低于 5 mm pair、负距离 pair 和最近 body/geom。

冻结参数为：

| 参数 | 值 |
|---|---:|
| minimum distance | `0.005 m` |
| detection distance | `0.020 m` |
| gain | `0.85` |
| bound relaxation | `0` |
| broadphase | `true` |
| geom pair count | `362` |

该约束是当前姿态附近的线性化速度约束；它在目标动作、关节速度信赖域和其他 IK limits 同时存在时求折中，不是对下一姿态进行迭代式硬投影。因此“约束已加入”和“所有输出都满足 5 mm”是两个不同命题。

## 4. 实验设计

比较对象为：

- A1：冻结 Temporal-GMR v2；
- A2：A1 + Collision-GMR v1；
- 开发集：Step-10 的 15 条、90,540 帧；
- 正式集：I0 之前预注册且与开发动作名称互斥的 15 条、91,627 帧。

开发结果通过后才解封 held-out；A2 参数和核心实现未根据 held-out 输出调整。两组均使用同一个冻结质量评价器。预注册主要指标为 `self_collision_nonhand_frame_rate` 和 `self_collision_nonhand_event_count`；附加门控为无新增 hard-fail、总体 fidelity pass rate 下降不超过 `0.02`，并保持突跳率和速度超限率为 0。未使用未校准综合质量分数。

## 5. 结果

### 5.1 主要门控

| 数据 | 指标 | A1 | A2 | A2-A1 |
|---|---|---:|---:|---:|
| 开发 | 非手部碰撞帧率 | `0.02435388` | `0.01814668` | `-0.00620720` |
| 开发 | 非手部碰撞事件 | `572` | `563` | `-9` |
| 开发 | fidelity pass rate | `0.86528606` | `0.86497681` | `-0.00030926` |
| held-out | 非手部碰撞帧率 | `0.01996137` | `0.01467908` | `-0.00528229` |
| held-out | 非手部碰撞事件 | `542` | `488` | `-54` |
| held-out | fidelity pass rate | `0.88753315` | `0.88739127` | `-0.00014188` |

开发和 held-out 的 A1/A2 hard-fail 均为 12/15，均无新增动作；两组的突跳率和速度超限率均保持为 0。开发集 motion-level bootstrap 中，碰撞帧率差的 95% CI 完全低于 0，但事件数差的 CI 跨 0；held-out 上两项 CI 均低于 0。开发集的“事件减少”证据弱于“持续帧减少”，这一点不能省略。

正式机器结果见：

- 开发比较：[`comparison_summary.json`](../outputs/collision_gmr_development_v1_comparison_v2/comparison_summary.json)
- held-out 比较：[`comparison_summary.json`](../outputs/collision_gmr_heldout_a2_v1_comparison/comparison_summary.json)
- held-out 逐动作：[`paired_motion_metrics.csv`](../outputs/collision_gmr_heldout_a2_v1_comparison/paired_motion_metrics.csv)
- held-out 逐类别：[`category_metrics.csv`](../outputs/collision_gmr_heldout_a2_v1_comparison/category_metrics.csv)

### 5.2 pair 覆盖与 signed-distance 独立审计

held-out 质量事件按冻结 body-pair 覆盖拆分后：

| 事件口径 | A1 | A2 | 变化 |
|---|---:|---:|---:|
| 被 193 个审计 body pair 覆盖的事件 | `379` | `332` | `-47` |
| 未覆盖的结构近邻事件 | `163` | `156` | `-7` |
| 覆盖 pair 的事件帧实例 | `1856` | `783` | `-1073` |

主要下降来自真正进入约束的 pair；未覆盖项的小幅变化属于 IK 的间接耦合，不能解释为这些 pair 也被直接约束。覆盖审计见 [`event_coverage_audit.json`](../outputs/collision_gmr_heldout_a2_v1_event_audit/event_coverage_audit.json)。

另一个独立工具不使用 MuJoCo contact 事件聚合，而是把 A1/A2 qpos 放回派生模型，对全部 362 个 geom pair 重算 signed distance。held-out 结果为：

| 几何口径 | A1 | A2 | 变化 |
|---|---:|---:|---:|
| 低于 5 mm 的帧 | `2184` | `2047` | `-137` |
| 负距离帧 | `1183` | `677` | `-506` |
| 负距离 pair-frame | `1943` | `793` | `-1150` |
| 穿透 pair 事件 | `399` | `340` | `-59` |
| 最坏 signed distance | `-88.14 mm` | `-41.62 mm` | 改善但仍穿透 |

开发集也呈一致方向：负距离帧 `1543 -> 914`，最坏距离 `-99.49 -> -33.20 mm`；但低于 5 mm 的 pair 事件为 `857 -> 857`。完整几何结果见 [`geometry_audit_summary.json`](../outputs/collision_gmr_heldout_a2_v1_geometry_audit/geometry_audit_summary.json)。

### 5.3 副作用和反例

held-out 总体副作用均按原值保留：

- ground penetration frame rate 增加 `0.00019645`；
- severe ground penetration 增加 `0.00008731`；
- undesired ground contact 增加 `0.00007640`；
- foot slide 增加 `0.00001091`；
- 近 2% 限位帧率反而下降 `0.00007640`。

逐动作并非单调改善：

- `walk3_subject3` 碰撞帧率明显下降，但事件数 `61 -> 69`，说明长事件可能被缩短并碎片化；
- `ground1_subject4` 事件 `30 -> 33`；
- `obstacles1_subject2` 事件 `29 -> 33`；
- `walk3_subject3` fidelity pass rate 下降约 `0.00189`，但仍远低于总体 0.02 门限。

12/15 hard-fail 数量没有下降，说明当前失败标签还由严重穿地、非预期触地、持续碰撞等多因素共同决定；只加自碰撞约束不足以解决完整数据质量问题。

## 6. 复现与可视化

所有命令都在 `/root/gpufree-data/gmr_improved` 下执行，输出目录必须是新的空目录。

```bash
PYTHONPATH=src conda run -n gmr python -m gmr_improved.collision_model_cli \
  --source-xml /root/gpufree-data/GMR/assets/unitree_g1/g1_mocap_29dof.xml \
  --output-dir assets/<new_collision_model_dir>

PYTHONPATH=src conda run -n gmr python -m gmr_improved.collision_cli \
  --config configs/collision_gmr_heldout_v1.yaml \
  --output-dir outputs/<new_collision_heldout_dir>
```

项目已生成 `dance1_subject2` 的非破坏性 viewer 兼容副本，可直接回放：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/visualization_compat/dance1_subject2_a2_collision_v1.pkl
```

与 A1 对照：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/visualization_compat/dance1_subject2_a1.pkl
```

为其他 A2 动作创建兼容副本时使用 [`viewer_compat_cli.py`](../src/gmr_improved/viewer_compat_cli.py)，它拒绝覆盖目标并逐元素验证核心轨迹未改变。

## 7. 科研边界与下一步

本实验支持“经过 pair 审计的碰撞速度约束能够降低 GMR/Temporal-GMR 的非手部自碰撞持续时间和穿透程度”。它不支持以下更强结论：

- A2 严格无碰撞或始终保有 5 mm 安全余量；
- 排除的手部/结构近邻接触都合理；
- MuJoCo 运动学回放中的改善会自动转化为动力学可执行性；
- A2 已提高模仿学习或技能学习的成功率。

后续 I2 应固定 A0/A1/A2 和质量指标，构建不使用测试结果调参的数据分层，再用同一策略结构、训练预算和多随机种子验证数据质量与下游学习价值。若后续继续研究碰撞算法，应作为新版本单独预注册，可考虑迭代式逐帧安全投影、penetration recovery slack、根部自由度约束，以及足底穿透/接触一致性联合约束；不得覆盖本次 v1 负结果。
