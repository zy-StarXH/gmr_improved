# Temporal-GMR（I0）独立测试与最终报告

## 1. 结论

Temporal-GMR v2 已完成预注册的独立留出集检验，I0 门控通过。留出集包含 15 条未用于开发的 LAFAN1→Unitree G1 动作、91,627 帧，五类动作各 3 条。相对从同一批 BVH 重新生成的原始 GMR（A0），Temporal-GMR（A1）：

- 将关节突跳率从 1.643% 降至 0；
- 将速度超限率从 11.370% 降至 0；
- 将近 2% 限位帧率从 57.926% 降至 56.142%；
- 未产生新的 hard-fail 动作；
- 总体 fidelity pass rate 从 90.199% 降至 88.753%，下降 1.446 个百分点，仍在预注册的 2 个百分点容许范围内。

因此，I0 所定义的“整帧速度信赖域、跨帧正则、软限位余量”实现与独立测试均已完成。该结论只说明运动学轨迹的时序约束指标达到门控，不代表碰撞、接触、动力学可执行性或下游模仿学习性能已经解决。

未校准 `quality_score` 没有参与调参、样本筛选、门控或结论。

## 2. 证据边界

### 2.1 代码直接确认

- 整帧速度信赖域以实际上一输出帧为共同参考，限制全部内部 IK 迭代的累计关节位移，而不是为每次内部迭代重新分配预算。
- v2 的关节速度上界为 `9.41535318280861 rad/s`，即冻结评价阈值 `3π rad/s` 的 0.999；浮动根不计入该关节速度约束。
- 跨帧正则目标为上一实际输出姿态；软限位只在 3% 关节行程余量带外激活；原始硬关节限位仍保留。
- A0 使用原始 `GeneralMotionRetargeting(use_velocity_limit=false)`；A1 导入冻结的 Temporal-GMR v2 实现。两个参考项目均未被本任务修改。

### 2.2 留出数据支持

- 三项预注册主指标在留出集总体口径下严格改善。
- 15 条动作等权的固定 seed、10,000 次配对 bootstrap 中，突跳、速度超限和近限位的平均差 95% 区间均小于 0。
- fidelity 有可测量的下降，但总体下降未超过预注册门限；碰撞与接触类指标略有恶化。

### 2.3 本阶段不作出的结论

- 不把指标相关性写成算法对任务成功率的因果作用。
- 不声称 I0 已解决自碰撞、穿地、脚滑或接触保持。
- 不声称静态/运动学回放等价于动力学可执行。
- 不声称留出 15 条动作覆盖全部人体动作分布。

## 3. 冻结实验协议

开发阶段查看结果前已在 [`PLAN.md`](../PLAN.md) 预注册以下留出动作：

- standing/walking：`walk1_subject2`、`walk1_subject5`、`walk3_subject3`；
- running/jumping：`run1_subject5`、`run2_subject1`、`jumps1_subject1`；
- dance：`dance1_subject2`、`dance1_subject3`、`dance2_subject4`；
- complex dynamic：`obstacles1_subject2`、`fight1_subject2`、`multipleActions1_subject2`；
- floor motion：`ground1_subject4`、`fallAndGetUp1_subject5`、`pushAndFall1_subject1`。

冻结 catalog 为 [`data/temporal_gmr_heldout_sources.csv`](../data/temporal_gmr_heldout_sources.csv)，其 SHA-256 为 `35e5523c9f798a90745cbb6c92daa2785793f2a630a9775aef87bdd6f4900b03`。它与开发集动作名无交集，共 91,627 帧。

A0 与 A1 从相同完整 BVH 独立生成，均为 15 条、91,627 帧；质量评价使用冻结的同一配置，15/15 source pair 的 fidelity 均为 `enabled_verified`。突跳和速度使用 91,612 个有效相邻帧区间作为分母，其他帧率使用 91,627 帧。

预注册门控为：突跳率、速度超限率和近 2% 限位率严格下降；不新增 hard-fail 动作；总体 fidelity pass rate 下降不超过 0.02。参数未根据留出结果回调。

## 4. 独立测试结果

### 4.1 总体配对结果

| 指标 | A0 原始 GMR | A1 Temporal-GMR | A1−A0 | 门控解释 |
|---|---:|---:|---:|---|
| 关节突跳率 | 0.01642798 | 0 | -0.01642798 | 严格改善 |
| 速度超限率 | 0.11369690 | 0 | -0.11369690 | 严格改善 |
| 近 2% 限位帧率 | 0.57926157 | 0.56141749 | -0.01784409 | 严格改善 |
| 近 0.05 rad 限位帧率 | 0.65773189 | 0.65565827 | -0.00207362 | 改善 |
| 关节硬越界率 | 0 | 0 | 0 | 未新增 |
| fidelity pass rate | 0.90199395 | 0.88753315 | -0.01446080 | 在 0.02 门限内 |
| hard-fail 动作数 | 12/15 | 12/15 | 无新增/无消除 | 通过安全门控 |

A1 的最大观测关节速度为 `9.415353182808618 rad/s`，最大信赖域占用比为 `1.0000000000000007`，在数值审计容差内；冻结评价器得到 0 个速度超限区间。最大单帧关节步长从 `1.0783 rad` 降至 `0.3138 rad`。

按 15 条动作等权平均，joint acceleration p95 从 `85.5018` 降至 `81.4041 rad/s²`，joint jerk p95 从 `3096.0047` 降至 `2985.3448 rad/s³`。这两个统计支持平滑性改善，但不属于预注册的三项严格门控。

### 4.2 配对 bootstrap

固定随机种子、10,000 次 motion-level 配对 bootstrap 的动作等权平均差如下：

| 指标 | 平均 A1−A0 | 95% CI |
|---|---:|---:|
| 关节突跳率 | -0.01986096 | [-0.04337446, -0.00526177] |
| 速度超限率 | -0.12120611 | [-0.18701275, -0.06808867] |
| 近 2% 限位率 | -0.01803363 | [-0.02744273, -0.00978093] |
| fidelity pass rate | -0.01661045 | [-0.03238677, -0.00583039] |

这些区间描述当前 15 条动作间的配对差异，不是对任意动作总体的分布无关保证。

### 4.3 类别差异

五类动作的突跳和速度超限均降为 0，近 2% 限位率也均下降。standing/walking 的 fidelity 仅下降 0.017 个百分点；complex dynamic、floor motion、running/jumping 分别下降 1.830、0.509、0.821 个百分点；dance 下降 5.116 个百分点。

dance 的速度超限率下降 25.474 个百分点、近限位下降 2.940 个百分点，但同时非手部自碰撞、穿地和脚滑分别增加 0.614、0.675 和 0.648 个百分点。固定速度信赖域对高速舞蹈动作的 tracking/contact trade-off 明显强于其他类别。

### 4.4 负结果与副作用

总体副作用必须与主指标同时报告：

| 指标 | A0 | A1 | A1−A0 |
|---|---:|---:|---:|
| 非手部自碰撞帧率 | 0.01886998 | 0.01996137 | +0.00109138 |
| 穿地帧率 | 0.08574983 | 0.08796534 | +0.00221550 |
| 严重穿地帧率 | 0.02123828 | 0.02211139 | +0.00087311 |
| 非预期触地帧率 | 0.08200640 | 0.08243203 | +0.00042564 |
| 脚滑帧率 | 0.02497081 | 0.02667336 | +0.00170255 |

平均 key-body 位置误差增加 `0.000579 m`，末端位置误差增加 `0.000892 m`，link orientation 误差增加 `0.149836°`。

最明显反例为 `dance1_subject2`：fidelity pass rate 下降 10.672 个百分点，同时非手部自碰撞、穿地和脚滑分别增加约 1.698、1.521 和 1.622 个百分点。该动作的速度违规得到强改善，但说明单一固定时序约束不能兼顾所有高速动作的 tracking 与接触合理性。该反例完整保留，并作为后续 I1/I2 的重点诊断样本。

## 5. 验证、审计与可复现性

- 测试：`21 passed`；`compileall` 通过。warning 仅来自外部 Torch JIT deprecation。
- 核心独立审计 [`data/temporal_gmr_heldout_core_audit.json`](../data/temporal_gmr_heldout_core_audit.json) 为 `ok=true`、0 mismatch。
- A0/A1 生成均为 15 条、91,627 帧；A0/A1 质量输出均为 18 项；比较输出为 5 项；全部 manifest 哈希匹配。
- 比较 summary 明确记录 `uncalibrated_quality_score_used=false`。
- 冻结 v2 实现哈希保持不变：`temporal.py=c00b37167acc0cf5679a52bbc24c354874a63e5d43560ba986f5109c0ae148a0`，`temporal_experiment.py=bdb5aa9b6086daa18741616aa9162aa9e3b84e108b467372f2b4f588598ae746`。
- GMR 参考提交仍为 `bb1bbe40774794fceb2a7c579a3464a28e68c844`；任务开始前已有的 dirty 文件保持原样。

核心机器可读入口：

- [`comparison_summary.json`](../outputs/temporal_gmr_heldout_comparison_v1/comparison_summary.json)
- [`paired_motion_metrics.csv`](../outputs/temporal_gmr_heldout_comparison_v1/paired_motion_metrics.csv)
- [`category_metrics.csv`](../outputs/temporal_gmr_heldout_comparison_v1/category_metrics.csv)
- [`comparison_manifest.json`](../outputs/temporal_gmr_heldout_comparison_v1/comparison_manifest.json)

## 6. 如何可视化检查完成情况

推荐从 [`outputs/temporal_gmr_heldout_visualization_v3/index.html`](../outputs/temporal_gmr_heldout_visualization_v3/index.html) 查看最终可视化包。它包含：测试链路 PASS 总览、总体 A0/A1 指标、副作用、类别热图、逐动作 smoothness/fidelity 权衡以及 `dance1_subject2` 时间线。

在有浏览器的环境中运行：

```bash
cd /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_visualization_v3
python -m http.server 8000
```

然后访问 `http://127.0.0.1:8000/`。完整说明见 [`VISUALIZATION_GUIDE.md`](../outputs/temporal_gmr_heldout_visualization_v3/VISUALIZATION_GUIDE.md)。

MuJoCo 可分别回放同一留出动作的 A0 与 A1。A0 示例：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a0_v1/retargeted/dance1_subject2.pkl
```

A1 将路径中的 `temporal_gmr_heldout_a0_v1` 改为 `temporal_gmr_heldout_a1_v1`。GUI 回放需要图形桌面。建议分别录屏后并排比较关节瞬时跳变和高速段连续性，同时用时间线与量化门控确认；肉眼回放不能替代指标审计。

## 7. 后续研究

I0 完成后，下一预注册组件是 I1 Collision-GMR。I1 应基于经模型等价性审计的非相邻碰撞 pair，在不回调 I0 留出结果的前提下验证能否降低自碰撞，并继续报告 fidelity、穿地和脚滑副作用。Contact-GMR（I2）与下游机器人学习验证仍未开始。
