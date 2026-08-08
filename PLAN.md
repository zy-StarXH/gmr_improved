# GMR 失败案例分析与渐进约束改进计划

## 0. 执行规则

本文件是 `/root/gpufree-data/gmr_improved` 的首要执行入口。每次任务必须先阅读本文件，开始时更新状态，结束时补充实际命令、结果、负结果和产物哈希。

- 所有新增代码、配置、报告与实验结果只写入本项目。
- `/root/gpufree-data/GMR` 和 `/root/gpufree-data/retargeting_quality_assessment` 只读使用。
- 不使用未校准 `quality_score` 选择或解释失败案例。
- 结论分为“代码直接确认”“数据支持”“待验证假设”，相关性不得写成因果关系。
- 不删除异常样本，不在查看改进结果后更换正式测试集或主要评价口径。
- 正式命令只能写入新的空输出目录；已完成并进入 manifest 的输出不得覆盖。

## 1. 研究目标与当前证据

本阶段首先完成课题流程第 3 步：用已有基础指标系统分析 GMR 失败案例，确认最值得解决的问题，并为第 4 步预注册可检验的改进路线。

冻结输入为 Step 10 的 15 条 LAFAN1→Unitree G1 轨迹，共 90,540 帧。实施前只读核对得到：

- 15/15 条存在速度超限和关节突跳；全部突跳帧同时速度超限；
- 近限位影响全部轨迹，轨迹级中位帧率为 56.4%；
- 持续非手部自碰撞影响 11/15 条，严重穿透影响 8/15 条；
- GMR 使用 XML 关节硬限位，但冻结生成显式设置 `use_velocity_limit=false`；
- 当前实现没有碰撞约束、接触保持或跨帧平滑目标，并允许每帧进行多次局部 IK 积分；
- Mink 1.2.0 提供 `CollisionAvoidanceLimit`，但当前 G1 XML 除地面外的碰撞 geom 没有唯一名称，接入前必须生成并验证派生模型。

这些是正式分析的起点，不代替最终产物中的重新计算与核验。

## 2. 状态表

| ID | 工作项 | 状态 | 验收产物 |
|---|---|---|---|
| S0 | 建立计划、项目骨架与冻结配置 | completed | `PLAN.md`、`pyproject.toml`、配置 |
| S1 | 实现只读基线分析 CLI 与单元测试 | completed | `src/`、`tests/` |
| S2 | 运行正式定量分析与失败窗口生成 | completed | `outputs/baseline_failure_analysis_v2/` |
| S3 | 结构化视觉核验与根因证据分级 | completed | review YAML、案例目录 |
| S4 | 完成第 3 步研究报告 | completed | `reports/GMR_FAILURE_ANALYSIS.md` |
| S5 | 测试、哈希与最终验收 | completed | pytest、manifest 复核、执行日志 |
| I0 | 第 4 步 Temporal-GMR | completed | 整帧速度信赖域、跨帧正则、软限位余量、独立配对实验与审计 |
| I1 | 第 4 步 Collision-GMR | completed | 派生 XML、非相邻 pair 审计、碰撞约束、开发/独立留出 A1/A2 配对实验与审计 |
| I2 | 第 4 步 Contact-GMR | completed | 接触感知足底保持、根高度穿透修正、A2/A3 开发与独立留出配对实验 |

状态只允许使用 `pending / in_progress / completed / blocked / preregistered`。第 3 步完成不等于第 4 步算法已经有效。

## 3. 第 3 步实施规范

### 3.1 冻结与溯源

分析程序必须核对 catalog、质量汇总、事件表、评价配置、GMR 核心实现、IK 配置和 G1 XML 的 SHA-256，并确认：

- 15 条轨迹、5 类各 3 条；
- 总帧数 90,540；
- 全部 source pair 为 `verified_generated_exact`；
- GMR 提交为 `bb1bbe40774794fceb2a7c579a3464a28e68c844`；
- 输入契约要求有限的字段不含 NaN/Inf，逐帧文件与 summary 帧数一致；导数开头和不可用 fidelity/IK 字段允许保留有定义的 NaN。

任何不一致都必须中止正式分析并记录，不能静默放宽。

### 3.2 定量分析

正式分析忽略综合分数，分别输出：

- 每轨迹、每动作类和全队列的突跳、速度、近限位、自碰撞、穿透、非预期触地和脚滑；
- 关节与碰撞 body-pair 热点；
- 事件次数、涉及帧数、持续时间和最大严重度；
- 异常交集、条件比例和 Jaccard；
- `feet_only` 与 `floor_motion` 的接触语义分层结果。

事件持续时间之和可能包含重叠，只能描述事件负担；帧率必须从逐帧布尔量重新计算。

### 3.3 冻结失败窗口与视觉复核

在查看新生成的局部姿态图之前，由程序固定 12 个窗口：

- 非手部自碰撞 4 个；
- 地面穿透 3 个；
- 关节突跳 3 个；
- `walk1_subject1`、`jumps1_subject5` 各 1 个低异常对照。

异常窗口按最大严重度、持续时间、motion name 稳定排序，同类内优先不同动作；每个窗口覆盖事件前后各 1 秒，并固定 5 个姿态帧。人工复核字段为：

- `visible_artifact`: `confirmed / partial / likely_metric_artifact / uncertain / control_plausible`；
- `metric_agreement`: `agree / partial / disagree / not_applicable`；
- `notes`：必须陈述可见与数值证据及限制；
- `reviewer`、`reviewed_at`。

静态 FK 不能证明动力学可执行性。相邻连杆固有重叠、floor-motion 合理触地和 contact proxy 不确定性必须单独记录。

### 3.4 根因证据分级

- 突跳：对照源目标连续性、机器人关节 step/velocity、IK error 和限位余量；
- 近限位：区分硬越界、长期贴边与数值容差；
- 自碰撞：区分非相邻穿插、相邻连杆模型重叠和允许手部接触；
- 穿地：区分根高度、足部姿态和地面动作语义；
- 脚滑：检查接触代理与 MuJoCo contact 一致性。

小规模速度开关、迭代次数或根高度投影只可作为原因诊断，不计作正式改进结果。

## 4. 第 4 步预注册路线

采用用户确认的渐进约束方案，保持 GMR/Mink 主框架：

1. **A0 原始 GMR**：完全复现冻结基线。
2. **A1 Temporal-GMR**：对整帧总位移实施速度信赖域，增加上一帧姿态正则与软关节限位余量；约束必须作用于最终相邻输出帧，不能只限制一次内部迭代。
3. **A2 Collision-GMR**：在 A1 上加入经审计的非相邻碰撞 pair；派生 XML 只补唯一 geom 名称，必须通过模型和 FK 等价性测试。
4. **A3 Contact-GMR**：在 A2 上用人体足部高度/速度与迟滞推断接触段，保持站立脚并平滑修正最小根高度；`floor_motion` 使用独立语义策略。

开发只使用当前 Step 10 队列。正式测试在查看改进结果前冻结以下 15 条未使用 LAFAN1 动作：

- standing/walking：`walk1_subject2`、`walk1_subject5`、`walk3_subject3`；
- running/jumping：`run1_subject5`、`run2_subject1`、`jumps1_subject1`；
- dance：`dance1_subject2`、`dance1_subject3`、`dance2_subject4`；
- complex dynamic：`obstacles1_subject2`、`fight1_subject2`、`multipleActions1_subject2`；
- floor motion：`ground1_subject4`、`fallAndGetUp1_subject5`、`pushAndFall1_subject1`。

组件仅在目标指标改善、未新增 hard-fail，且全体 fidelity pass rate 下降不超过 2 个百分点时进入下一层。正式报告给出逐动作配对差、类别结果与 bootstrap CI，不使用未校准总分代替各基础指标。

## 5. 第 3 步完成条件

- `analyze-baseline` 对 15/15 条成功运行，逐帧合计为 90,540；
- summary 中的关键帧率由逐帧表独立重算一致；
- 12 个窗口选择可重复，姿态图和时间线齐全；
- 报告中每个数值可追溯到机器可读表；
- 所有正式输出进入 manifest 且 SHA-256 独立复核通过；
- 相关测试、`compileall`、`pip check` 通过；
- 任何负结果原样保留。

## 6. 执行日志

### 2026-08-05 17:04 CST — S0 开始

- 已阅读 `retargeting_quality_assessment/QUALITY_ASSESSMENT_REPORT.md`、Step 10 报告、冻结 summary/events/frame metrics、GMR IK 实现与 G1 XML。
- 用户选择“渐进约束改进”，本轮先完成第 3 步。
- 输入项目已有正式结果保持只读；GMR 工作树已有 1 个修改文件和 2 个未跟踪文件，均不处理。
- 当前下一动作：创建冻结配置、分析 CLI 与测试。

### 2026-08-05 17:05 CST — S0 完成、S1 开始

- 已建立 Python 项目骨架、冻结配置、只读分析 CLI 和初始单元测试。
- 本地 `/root/gpufree-data/GMR` 被明确作为 A0 参考实现；用户再次确认该路径可供参考。
- 改进代码仍只允许写入 `gmr_improved`，A0 后续必须与该 GMR 参考实现做逐元素一致性验证。
- 当前下一动作：运行单元测试和正式分析冒烟，修正实现问题后进入 S2。

### 2026-08-05 17:06 CST — S1 完成、S2 开始

- `PYTHONPATH=src conda run -n gmr python -m pytest -q`：4 passed。
- `compileall`：退出码 0。
- CLI 已实现输入哈希/提交校验、逐帧重算、分层统计、热点/共现分析、冻结案例选择、静态 FK 图和输出 manifest。
- 当前下一动作：向新的正式目录运行冻结基线分析。

### 2026-08-05 17:07 CST — S2 首次运行被门控拒绝

- 正式分析在写出统计表前中止：突跳与速度超限重算率和冻结 summary 不一致；其余五项一致。
- 已定位为分母口径错误：一阶差分只有 `T-1` 个有效区间，不能用全部 `T` 帧作分母。
- 失败目录仅包含 3 个空子目录，无正式文件；将清理空目录后使用相同正式路径重跑。
- 修正要求：输出同时记录 flagged count、eligible count 和 rate，并增加 `T-1` 单元测试。

### 2026-08-05 17:08 CST — S2 完成、S3 开始

- 修正后测试：5 passed；正式分析成功处理 15 条、90,540 帧。
- 输出 48 个 manifest 文件；独立复核 `ok=true`、0 mismatch。
- 基础量：突跳 1,980 个区间、速度超限 8,783 个区间、近限位 49,426 帧、非手部自碰撞 2,190 帧、穿地 9,497 帧、严重穿地 3,555 帧、脚滑 2,679 帧。
- hard-fail 影响：持续自碰撞 11/15、严重穿透 8/15、feet-only 非预期触地 7/15。
- 已冻结并生成 12 个局部窗口；当前下一动作：按协议完成视觉复核和根因证据分级。

### 2026-08-05 17:11 CST — S3 完成、S4 开始

- 已按冻结协议查看 12 组姿态 montage 和指标时间线；10 个异常窗口为 6 confirmed、4 partial，指标一致性 7 agree、3 partial。
- 2 个无 hard-fail 对照均保持可解释姿态；`jumps1_subject5` 对照中仍有孤立速度峰值，已原样记录。
- 视觉 review 与案例 catalog 通过 CLI 一对一校验并合并为 `reports/FAILURE_CASE_CATALOG.csv`；测试增至 6 passed。
- 已形成 `data/root_cause_evidence.yaml`，把代码事实、数据支持和待验证因果假设分开。
- 当前下一动作：完成主报告并执行最终交付验收。

### 2026-08-05 17:14 CST — 最终验收前的 manifest 缺口

- 已完成主报告草稿，但发现 `baseline_failure_analysis/run_manifest.json` 未记录生成分析的本项目源码哈希。
- 原结果保留、不覆盖；它的统计和 48 个输出哈希仍有效，但不作为最终复现入口。
- 修正为分析版本 `step3_failure_analysis_v1.1`，manifest 增加 `analysis.py`、`cli.py`、`__init__.py` 的路径、大小和 SHA-256。
- 将在新目录 `outputs/baseline_failure_analysis_v2` 重跑，并要求核心机器可读表与 v1 逐字节一致。

### 2026-08-05 17:23 CST — S4 完成、S5 开始

- v2 正式分析完成：15 条、90,540 帧、48 个输出文件；输出 manifest 复核 0 mismatch，3 个分析源码哈希复核 0 mismatch。
- v1/v2 的 8 个机器可读 CSV 表 SHA-256 全部一致；证据写入 `data/v1_v2_equivalence.json`。
- 正式视觉合并表更新为 `reports/FAILURE_CASE_CATALOG_v2.csv`，与 v2 冻结案例逐项一致。
- 主报告已完成，明确区分代码事实、数据支持、待验证假设，并将 A1–A3 保持为未实施的预注册路线。
- 当前下一动作：执行 pytest、compileall、pip check、输出/源码哈希及交付清单的最终验收。

### 2026-08-05 17:25 CST — S5 完成，第 3 步验收通过

- `PYTHONPATH=src conda run -n gmr python -m pytest -q`：7 passed。
- `PYTHONPATH=src conda run -n gmr python -m compileall -q src tests`：退出码 0。
- `conda run -n gmr python -m pip check`：No broken requirements found。
- v2 输出 manifest：48/48 文件，0 mismatch；分析源码：3/3 文件，0 mismatch。
- v2 正式表中不存在 `quality_score` 字段；12/12 视觉 review 与冻结案例一一对应。
- 正式关键哈希：`run_manifest.json=4206a1d2...13dc`，`GMR_FAILURE_ANALYSIS.md=22326b49...b1a`，`FAILURE_CASE_CATALOG_v2.csv=51c56601...031`。
- 第 3 步正式完成。下一任务必须从本文件开始，先复核上述交付与冻结 A0，再进入 I0/Temporal-GMR；I0–I2 当前仍是预注册、未实施状态。

### 2026-08-05 17:53 CST — I0 开始

- 已按执行规则重新阅读全文，并将 I0 状态改为 `in_progress`；I1/I2 保持预注册、未实施。
- A0 冻结输入仍为 Step 10 的 15 条、90,540 帧；A1 不改写 `/root/gpufree-data/GMR`，全部实现和结果只写入本项目。
- I0 的整帧速度约束口径锁定为相邻 30 Hz 输出帧的可动关节总位移上界，而非 MuJoCo `0.002 s` 内部单步上界；配置上界必须被逐帧审计。
- 跨帧正则只作为软目标，目标为上一输出帧；软限位余量只产生靠近限位时的内向目标，不取代原始硬关节限位，不允许用硬裁剪掩盖求解失败。
- 开发比较继续使用冻结 Step 10 队列并复用已有 A0；查看 A1 开发结果后不得修改第 4 节已冻结的 15 条正式测试动作。
- 当前下一动作：实现约束/任务、兼容 GMR 的时序重定向器、运行器与不变量测试。

### 2026-08-05 18:05 CST — I0 实现与冒烟门控

- 已实现 `WholeFrameVelocityLimit`：每个 30 Hz 输出帧以“上一输出 qpos”为共同参考，对两阶段及全部内部 IK 迭代约束累计关节位移；浮动根按预注册口径不计入关节速度信赖域。
- 已实现上一输出姿态 `PostureTask` 软正则和分段二次 `SoftJointLimitTask`；第一帧禁用跨帧姿态代价，但仍保留原始任务与软限位目标。
- 新增独立 `temporal-gmr` CLI，未改动哈希冻结的 Step-3 `analysis.py`、`cli.py`、`__init__.py`；旧 manifest 源码哈希测试继续通过。
- A0 短前缀逐元素一致性测试通过；合成模型验证重复 6 次内部 IK 共享单个整帧预算；当前总测试为 12 passed。
- 首次冒烟按设计被最终帧审计拒绝。根因是 Mink 1.2 的 `solve_ik` 第六个位置参数是 `safety_break`，不是 `limits`；沿用上游位置参数写法会使新增 limits 未进入 QP。A1 已改为显式 `limits=...` 关键字，未改 GMR。
- 修正后 `walk1_subject1` 120 帧冒烟满足最大速度 `9.424777960769376 rad/s`、最大预算比 `0.9999999999999997`；质量评估得到 0 突跳、0 速度超限、0 关节硬越界、0 近 2% 限位帧。该前缀仅为工程检查，fidelity 状态为 `disabled_unverified_pair`，不作为效果结论。
- 当前下一动作：补全实现 manifest 覆盖与配对比较器，随后在 15 条冻结开发轨迹上运行 A1 和完整基础指标评估。

### 2026-08-05 18:19 CST — I0 v1 开发结果与 v2 数值余量预注册

- v1 完成 15 条、90,540 帧生成和冻结质量评估，15/15 fidelity 为 `enabled_verified`；A0/A1 hard-fail 均为 12 条且无新增动作。
- v1 的总体配对结果：突跳率 `0.0218724 -> 0`，速度超限率 `0.0970229 -> 0.0115990`，近 2% 限位率 `0.5459024 -> 0.5302518`，fidelity pass rate `0.8787939 -> 0.8653302`（下降 0.0134637，小于 0.02 门限）。因此 v1 按预注册开发门控通过。
- 速度超限剩余 1,050 帧的逐轨迹最大 excess 仅为 `1.776e-15` 至 `7.105e-15 rad/s`；这支持“QP 正好落在阈值、严格大于比较受浮点舍入影响”的数值解释，不代表观测到有物理量级的超限。
- 保留 v1 全部代码、结果与 manifest，不覆盖。v2 在查看其结果前只改变一个参数：把整帧速度上界固定为冻结评价阈值 `3*pi` 的 `0.999`，即 `9.41535318280861 rad/s`；跨帧代价、软限位代价/余量、数据与门控完全不变。
- v2 的目的仅是验证数值安全余量能否消除边界误报；即使 v2 失败，也必须保留并报告。当前下一动作：用 `configs/temporal_gmr_v2.yaml` 重跑完整开发集及配对评估。

### 2026-08-05 18:33 CST — I0 v2 冻结开发候选完成

- v2 完成 15 条、90,540 帧生成；逐帧最终预算审计通过，质量评估 15/15 成功且 fidelity 全部 `enabled_verified`。
- v2 结果：突跳 1,980→0、速度超限 8,783→0、近 2% 限位帧 49,426→48,011；关节硬越界仍为 0。
- 总体 fidelity pass rate `0.8787939 -> 0.8652861`，下降 0.0135078；A0/A1 hard-fail 都是 12/15，未新增动作。v2 通过预注册开发门控。
- 原样记录副作用：非手部自碰撞、穿地、严重穿地、脚滑帧率分别增加约 0.000166、0.000674、0.000585、0.000221；dance 和 running/jumping 的类别 fidelity 分别下降约 0.0249、0.0257。
- 逐动作反例：`dance2_subject2`、`sprint1_subject4` 的 fidelity 分别下降 0.0377、0.0605；`fallAndGetUp2_subject2` 的近 2% 限位率增加 0.000203。固定参数并非逐动作单调占优。
- v1/v2 独立哈希、形状、帧数、质量输出和信赖域审计均为 0 mismatch；测试为 15 passed，`compileall` 与 `pip check` 通过。
- I0 当前保持 `in_progress`：实现与冻结开发验证已完成，但第 4 节冻结的独立测试集尚未运行。下一动作必须先锁定 v2 代码/配置/manifest 哈希，再生成独立测试 A0/A1；不得依据其结果回调 v2。

### 2026-08-05 18:43 CST — I0 本轮最终验收

- `PYTHONPATH=src conda run -n gmr python -m pytest -q`：15 passed（仅有外部 torch JIT deprecation warnings）。
- `PYTHONPATH=src conda run -n gmr python -m compileall -q src tests`：退出码 0；`conda run -n gmr python -m pip check`：No broken requirements found。
- `TEMPORAL_DELIVERY_MANIFEST.json` 独立复核 24/24 文件、0 mismatch；v1/v2 嵌套审计各为 15 条、90,540 帧、0 mismatch。
- 哈希冻结的 Step-3 `analysis.py`、`cli.py`、`__init__.py` 保持原哈希；GMR 仍为提交 `bb1bbe4...`，仅存在任务开始前已有的 1 个修改和 2 个未跟踪文件。
- v2 冻结关键哈希：配置 `4a58ce6a...17eb5`、生成 manifest `a1d5d41a...3c51e`、质量 manifest `18a137ed...5a33`、比较 summary `f3a8bf6f...aa6c`、审计 `0b86ab96...6e60`。
- 本轮交付完成“实现 + 冻结开发验证”；I0 状态仍为 `in_progress`，唯一尚未完成的 I0 研究门控是预注册独立测试集。下一次执行必须先阅读本文件，并以 v2 上述哈希为不可回调候选。

### 2026-08-05 18:47 CST — I0 独立测试开始

- 已按规则重新阅读全文；用户要求继续完成 I0，并补充测试完成情况的可视化方法。
- 复核 v2 冻结候选未变化：`temporal.py=c00b3716...48a0`、`temporal_experiment.py=bdb5aa9b...e746`、`temporal_gmr_v2.yaml=4a58ce6a...17eb5`、开发生成 manifest=`a1d5d41a...3c51e`。
- 15 条预注册 held-out BVH 全部存在，共 91,627 帧；名称与 Step 10 开发集互斥，仍为五类各 3 条。每个源文件的 SHA-256 和 BVH 帧数已在查看任何独立测试输出前核对。
- 独立测试继续使用 v2 原参数和原 `TemporalGeneralMotionRetargeting` 源码，不允许依据结果调参；A0/A1 必须从相同完整 BVH 独立生成，质量评估配置与开发阶段相同。
- 正式验收口径不变：三项主指标严格下降、无新增 hard-fail、总体 fidelity pass rate 下降不超过 0.02；同时原样报告碰撞、穿地、接触和逐类别副作用。
- 当前下一动作：冻结 held-out catalog，建立不改动 v2 源码的 A0/A1 正式运行器与测试，然后向新的空目录执行。

### 2026-08-05 18:53 CST — held-out 输入与运行器冻结

- 已写入 `data/temporal_gmr_heldout_sources.csv`，SHA-256=`35e5523c...0b03`；15 条、91,627 帧、五类各 3 条，与开发 catalog 名称交集为空。
- 正式配置 `configs/temporal_gmr_heldout_v1.yaml` 锁定所有 BVH、GMR、XML、IK、质量配置以及 Temporal v2 源码/配置哈希；运行前审计 8 个冻结文件全部通过。
- 新运行器只导入冻结的 `TemporalGeneralMotionRetargeting`，不修改 `temporal.py`；A0 明确使用原 `GeneralMotionRetargeting(use_velocity_limit=false)`，A1 参数逐字段等于冻结 v2。
- `pytest`：17 passed；`compileall`：退出码 0。当前尚未读取任何 held-out 输出指标。
- 当前下一动作：先生成完整 A0，再生成完整 A1；两者必须各自写入新的空目录并保存独立 manifest。

### 2026-08-05 21:21 CST — held-out A0/A1、质量评价与配对门控完成

- A0 与 A1 均完成 15 条、91,627 帧独立生成；A1 最大观测关节速度为 `9.415353182808618 rad/s`，最大信赖域占用比为 `1.0000000000000007`。
- 同一冻结评价器完成 A0/A1 全量质量分析，15/15 fidelity 均为 `enabled_verified`；A0/A1 hard-fail 都是 12/15，无新增或消除动作。
- 留出总体结果：突跳率 `0.01642798 -> 0`，速度超限率 `0.11369690 -> 0`，近 2% 限位率 `0.57926157 -> 0.56141749`，fidelity pass rate `0.90199395 -> 0.88753315`（下降 `0.01446080`）。预注册 held-out gate 通过。
- 原样记录总体副作用：非手部自碰撞、穿地、严重穿地、非预期触地和脚滑帧率分别增加 `0.00109138`、`0.00221550`、`0.00087311`、`0.00042564`、`0.00170255`。
- `dance1_subject2` 是最明显反例：fidelity 下降约 10.672 个百分点，碰撞/穿地/脚滑均恶化；该结果不得因总体门控通过而删除。
- 当前下一动作：运行独立核心审计并生成只读可视化与最终报告；不得修改冻结候选或 held-out 结果。

### 2026-08-05 21:38 CST — held-out 核心独立审计完成

- `data/temporal_gmr_heldout_core_audit.json` 复核 A0/A1 生成、质量输出和比较产物，结果 `ok=true`、0 mismatch；确认比较未使用未校准综合分数。
- 关键 manifest：A0 生成 `88c802ac...e9cc`、A1 生成 `0d50848b...6565`、A0 质量 `13844b19...f0b9`、A1 质量 `1e1819eb...e69`、配对比较 `a6c8f334...313`。
- motion-level bootstrap 使用固定 seed、10,000 次重采样；三项主指标的平均差 95% CI 均小于 0，fidelity 的 CI 也表明存在真实 tracking trade-off。
- 当前下一动作：完成可视化布局复核、正式报告和最终交付清单。

### 2026-08-05 22:09 CST — I0 可视化与正式报告完成

- 保留可追溯的 v1/v2 可视化包及其布局问题，不覆盖；最终推荐包为 `outputs/temporal_gmr_heldout_visualization_v3`。已人工查看完成总览、总体指标、逐动作权衡和代表性时间线。
- v3 使用逐动作编号与 motion key 避免长标签遮挡；`visualization_manifest.json` SHA-256=`e3cb8a3c...36eab`。
- 正式结论写入 `reports/TEMPORAL_GMR_I0_FINAL_REPORT.md`，明确区分代码事实、留出数据支持、负结果和不作出的结论。
- `pytest`：21 passed；`compileall`：退出码 0。冻结 `temporal.py` 与 `temporal_experiment.py` 哈希未变化；GMR 仍为 `bb1bbe4...`，开始前已有 dirty 文件未处理。
- I0 状态更新为 `completed`。下一研究项为预注册的 I1 Collision-GMR，尚未开始；下游模仿学习验证仍不属于 I0 已完成结论。

### 2026-08-05 22:16 CST — I0 最终交付审计通过

- 新增最终交付清单 `I0_FINAL_DELIVERY_MANIFEST.json`，记录 28 个关键配置、源码、报告、核心 manifest、比较表和可视化入口；SHA-256=`1dc5974b...c68b`。
- `data/temporal_gmr_i0_final_audit.json` 对交付清单重新核验，结果 `ok=true`、0 mismatch、28/28 通过；SHA-256=`14ec0ae7...badc`。
- 另使用 `jq + sha256sum -c` 独立复算 28 个交付文件和 7 个 v3 可视化输出，全部 `OK`。
- 加入交付审计器自身的篡改检测测试后，最终 `pytest` 为 22 passed；`compileall` 通过，`pip check` 为 `No broken requirements found`。
- I0 无剩余必做项。以后执行 I1 前仍须先阅读全文；I1 不得把 I0 留出集结果当作可继续调节 Temporal-GMR v2 参数的开发反馈。

### 2026-08-05 22:23 CST — I0 MuJoCo 回放兼容性问题诊断

- 用户按最终报告中的命令调用 GMR `vis_robot_motion.py` 时，在加载阶段出现 `KeyError: local_body_pos`；尚未进入 MuJoCo 仿真。
- 只读核对确认 held-out A0 PKL 包含 `fps/root_pos/root_rot/dof_pos/dof_names`，其中 `dance1_subject2` 的数组形状为 `(3945,3)/(3945,4)/(3945,29)`，核心运动数据完整。
- GMR `load_robot_motion` 无条件读取 `local_body_pos` 与 `link_body_list`，而本项目 held-out 导出器未写入这两个仅供扩展数据集使用的兼容字段；原生 `bvh_to_robot.py` 即使没有相应数据也会把二者写为 `None`。
- 该问题属于可视化文件 schema 兼容性遗漏，不影响已完成的定量评价与 I0 门控。`xrobotoolkit_sdk not found` 只是可选 streamer 提示，与本次异常无关。
- 本轮只完成诊断和记录，未修改冻结 PKL、GMR、正式报告或 manifest。后续若实施修复，应新增独立 viewer/兼容副本和测试，不得覆盖已哈希冻结的 A0/A1 输出。

### 2026-08-05 22:28 CST — A0 回放兼容副本生成并验证

- 用户使用 `conda run -n gmr python - <<'PY'` 时没有出现预期 `Saved:` 输出；核对发现目标目录存在但 PKL 不存在。当前 Conda 捕获模式下 heredoc 未被可靠传递给 `python -`。
- 改用不依赖 stdin 的 `conda run -n gmr python -c`，生成新文件 `outputs/visualization_compat/dance1_subject2_a0.pkl`；未覆盖冻结 A0。
- 兼容副本只新增 `local_body_pos=None`、`link_body_list=None`。源文件 SHA-256=`2168cba6...1232`，兼容副本 SHA-256=`9c0eee4b...d8eb`。
- 使用原 GMR `load_robot_motion` 实际加载通过：fps=30，`root_pos/root_rot/dof_pos` 形状为 `(3945,3)/(3945,4)/(3945,29)`。GUI 尚未由自动任务启动，需用户在图形桌面运行查看器。

### 2026-08-05 22:32 CST — A1 回放兼容副本生成并验证

- 为相同 held-out 动作生成 `outputs/visualization_compat/dance1_subject2_a1.pkl`，只新增 `local_body_pos=None`、`link_body_list=None`，未覆盖冻结 A1。
- 冻结 A1 源文件 SHA-256=`85e25880...f0d5`，兼容副本 SHA-256=`1fc41a12...2a36`。
- 使用原 GMR `load_robot_motion` 加载通过：fps=30，`root_pos/root_rot/dof_pos` 形状为 `(3945,3)/(3945,4)/(3945,29)`。A0/A1 现可用同一查看器分别回放。

### 2026-08-05 22:36 CST — `dance1_subject2` A1 视觉扭曲/突变诊断

- 用户观察到 A1 比 A0 更扭曲且仍有可见突变。本轮只读比较原始冻结 PKL，不把肉眼现象直接等同于既有 `joint_jump_flag`。
- A1 最大关节步长为 `0.313845 rad/帧`，低于冻结突跳阈值 `0.5 rad/帧`，所以质量评价为 0 突跳；但 3,944 个区间中有 2,120 个区间的“任一关节最大步长”超过 `0.3 rad`，且 p95 已贴近信赖域上界。这会产生明显的限速饱和/阶梯感，说明当前二值门限不足以代表视觉平滑。
- 饱和最频繁的关节包括左右 wrist roll（695/525 个区间）、左右 shoulder yaw（477/441）、right wrist yaw（361）和 left knee（355）。固定全关节速度上界对高速舞蹈目标形成 tracking lag，并可能由其他关节/浮动根补偿。
- A1 片段内最大根平移步长为 `0.0611 m/帧`，最大根旋转步长为 `25.36°/帧`；Temporal v2 的信赖域和 `PostureTask` 均不约束 floating base。A1 最大根步长低于 A0 最大值，但仍足以在局部产生可见快速变化。
- GMR viewer 在第 3,944 帧后无条件回到第 0 帧。该非循环片段长 131.5 s，末帧到首帧的根位置差为 `4.83 m`、根旋转差 `29.30°`、最大关节差 `0.914 rad`；若突变每约 131.5 s 出现一次，它是播放器循环边界而非片段内部算法突跳。
- 视觉扭曲与冻结数据一致：该动作 fidelity pass rate `0.77085 -> 0.66413`，非手部自碰撞、穿地和脚滑率均恶化。I0 总体门控通过不表示该动作自然度改善；这是正式保留的反例，并提示后续需要连续型平滑指标、根部时序约束、加速度/jerk 正则及自适应约束，而不能只依赖 `0.5 rad` 二值突跳阈值。

### 2026-08-06 — I1 Collision-GMR 开始

- 已按执行规则重新阅读全文；用户明确要求开始实施“经过 pair 审计的非相邻碰撞约束”。I1 状态改为 `in_progress`，I0 冻结源码、参数、开发/留出结果均不回调。
- A2 必须继承冻结 Temporal-GMR v2，只新增 Mink 碰撞 limit；原 GMR、质量评价项目和原 G1 XML继续只读。
- 在查看 A2 开发结果前，先冻结：派生 XML 只补唯一 geom 名称（另允许为跨项目读取重定位 `meshdir`，编译模型必须数值等价）；pair 由机器人树拓扑机械生成；排除 world、同 body、树距离不超过 2 的近邻 body、MuJoCo contype/conaffinity 不相容 geom 与预注册允许手部接触；pair 清单进入机器可读审计。
- 派生模型必须先通过 `nq/nv/body/joint/geom` 结构一致、数值属性一致，以及多组确定性 qpos 下 body/geom FK 等价性测试。任何不一致先中止，不得运行效果实验。
- I1 开发阶段继续只使用 Step 10 的 15 条、90,540 帧；正式 held-out 仍使用 I0 前已冻结的 15 条、91,627 帧，但只有开发候选及参数锁定后才能解封。
- I1 主要目标为非手部非相邻自碰撞帧率/持续事件下降；同时要求不新增 hard-fail、总体 fidelity pass rate 相对 A1 下降不超过 0.02，并完整报告速度、限位、穿地、脚滑和逐动作副作用。未校准综合分数继续禁用。
- 在读取 A2 动作结果前冻结 Mink 参数：`minimum_distance_from_collisions=0.005 m`、`collision_detection_distance=0.020 m`、`gain=0.85`、`bound_relaxation=0`、`broadphase=true`。中立姿态审计只用于排除模型/规则错误，不用于动作效果调参。
- 当前下一动作：核对 Mink 1.2.0 `CollisionAvoidanceLimit` 契约、审计 G1 geom/body 拓扑和现有碰撞指标口径，然后锁定 pair 规则及距离参数。

### 2026-08-06 10:43 CST — I1 模型/pair 门控与 A2 冒烟完成

- 派生模型 `assets/collision_g1_v1/g1_mocap_29dof_collision_named.xml` 为 71 个原无名 geom 补充确定性唯一名称，并仅为跨项目读取重定位 `meshdir`。原/派生 `nq/nv/nbody/njnt/ngeom/nsite/nu/nmesh` 一致。
- 16 组固定 seed qpos 下 body、geom、site 的位置/姿态 FK 最大绝对差均为 0；模型数值数组审计 0 mismatch。模型 manifest SHA-256=`5ce1b187...6549`。
- pair 规则冻结为：排除 world、同 body、树距离 `<3`、允许手部 body 和 contype/conaffinity 不相容项；最终 193 个 body pair、362 个 geom pair。中立姿态 0 个 pair 低于 5 mm，最近距离 `0.00781156 m`；Mink 展开 362/362 一致。
- A2 继承冻结 Temporal-GMR v2，通过构造期临时模型路径重定向加载派生 XML，退出后恢复 GMR 全局映射；运行时 pair CSV 会逐行复核 geom ID/name/body/tree distance，并使用确定性 QP 行顺序。
- 冻结参数保持 `minimum=0.005 m`、`detection=0.020 m`、`gain=0.85`、零松弛、broadphase。正式开发配置 SHA-256=`520f82b8...3444`；核心实现 `collision.py=04b08b58...eb40`，runner=`8500e264...88b9`，CLI=`1dda38c8...dcd17`。
- 无碰撞 `walk1_subject1` 120 帧冒烟可解、速度预算通过；相对冻结 A1 最大关节数值差 `3.14e-4 rad`，说明额外 QP 行即使最终未激活也有微小数值扰动，不宣称逐元素 no-op。
- `multipleActions1_subject4` 300 帧激活冒烟中，A1 非手部碰撞为 1 帧/1 事件，A2 为 0；两者突跳/速度超限均为 0，近限位、穿地和脚滑相同。A2 有 5 帧低于 5 mm、最小 mesh distance 返回 0，但没有负距离 pair，说明 limit 未保证离散输出严格保持 5 mm。该短前缀 fidelity 未验证，仅为工程证据。
- 全项目测试 27 passed；`compileall`、`pip check` 通过。当前参数与代码在正式开发集前冻结，下一动作是在新目录运行完整 Step-10 A2 并用冻结评价器与 A1 v2 配对比较；不得根据开发结果静默覆盖 v1。

### 2026-08-06 11:02 CST — I1 冻结开发门控通过，held-out 解封

- A2 v1 完成冻结开发集 15 条、90,540 帧生成；速度信赖域审计通过。冻结质量评价 15/15 成功且 fidelity 全部为 `enabled_verified`。
- A1→A2 总体非手部碰撞帧率 `0.02435388 -> 0.01814668`，下降 `0.00620720`；非手部连续事件 `572 -> 563`。突跳率与速度超限率继续为 0，未新增 hard-fail；fidelity pass rate `0.86528606 -> 0.86497681`，下降 `0.00030926`，低于 0.02 门限。开发门控按预注册口径通过。
- 原样记录非单调性：`walk2_subject3` 碰撞事件 `69 -> 101`，`ground1_subject1` 为 `33 -> 49`；总体脚滑帧率增加 `0.00072896`，穿地增加 `0.00035343`，近 2% 限位率增加 `0.00001104`。开发通过不表示逐动作或所有次指标改善。
- A2 内部 362-pair 几何诊断发现 2,247 帧低于 5 mm、914 帧存在负 signed distance；Mink 瞬时线性速度 limit 降低统计碰撞，但没有对离散输出提供严格无穿透保证。该负结果必须保留，后续不得改写为“完全消除碰撞”。
- 质量事件按审计 body-pair 覆盖拆分：A1/A2 受约束 pair 的事件数 `409 -> 402`、逐 motion 去重帧和 `1543 -> 913`；未纳入的树近邻 pair 事件 `163 -> 161`、去重帧和 `893 -> 841`。事件数下降较小而持续帧下降明显，表明 v1 更接近缩短碰撞持续时间，同时可能产生事件碎片化。
- v1 参数与核心实现保持冻结。正式配置 `configs/collision_gmr_heldout_v1.yaml` SHA-256=`0a5aa5b5...013b`，直接复用 `collision.py=04b08b58...eb40`、runner=`8500e264...88b9` 和 I0 预注册 held-out catalog（15 条、91,627 帧）；配置在查看任何 A2 held-out 输出前写入并校验。
- 当前下一动作：在全新目录生成 held-out A2，用同一冻结评价器与既有 held-out A1 配对比较；不得依据 held-out 结果回调 v1。

### 2026-08-06 11:25 CST — I1 held-out 验证与最终交付完成

- A2 使用冻结 v1 在预注册 held-out 15 条、91,627 帧上完整生成；速度信赖域审计通过。质量评价 15/15 成功、fidelity 全部 `enabled_verified`，A1/A2 hard-fail 均为 12 条且无新增动作。
- held-out 主要指标：非手部碰撞帧率 `0.01996137 -> 0.01467908`，连续事件 `542 -> 488`；motion-level bootstrap 两项 95% CI 均小于 0。突跳率与速度超限率保持 0，fidelity pass rate 仅下降 `0.00014188`，正式门控通过。
- pair 覆盖审计确认主要变化来自受约束 pair：覆盖 body pair 的事件 `379 -> 332`、事件帧实例 `1856 -> 783`；未覆盖树近邻事件 `163 -> 156`。审计 SHA-256=`c479e070...64ad`。
- 独立 362-pair signed-distance 审计：低于 5 mm 帧 `2184 -> 2047`，负距离帧 `1183 -> 677`，负 pair-frame `1943 -> 793`，最坏距离 `-88.14 -> -41.62 mm`。A2 仍有 677 个穿透帧是冻结负结果，故结论限定为降低持续时间/程度，不写成严格自碰撞避免。审计 SHA-256=`b01d085a...f433`。
- 原样记录副作用：穿地、严重穿地、非预期触地和脚滑帧率分别增加 `0.00019645`、`0.00008731`、`0.00007640`、`0.00001091`；`walk3_subject3`、`ground1_subject4`、`obstacles1_subject2` 的碰撞事件数分别增加 8、3、4。12/15 hard-fail 不变说明单一碰撞约束没有解决完整质量问题。
- 最终报告为 `reports/COLLISION_GMR_I1_FINAL_REPORT.md`（SHA-256=`4559c146...03c8`）；A2 `dance1_subject2` viewer 兼容副本通过原 GMR loader 验证，SHA-256=`22396d4d...2de8`，未覆盖冻结 PKL。
- 全项目 `pytest` 为 35 passed；`compileall` 通过；`pip check` 为 `No broken requirements found`。I1 交付 manifest SHA-256=`54a469d4...e65c`，最终审计 `ok=true`、37/37 文件、0 mismatch，审计文件 SHA-256=`7b132ad3...bc5`。
- GMR 仍为提交 `bb1bbe4...`，开始前已有的 1 个修改文件和 2 个未跟踪文件未处理；质量评价项目保持只读。I1 状态更新为 `completed`。
- 下一项为 I2 Contact-GMR。开始前必须重新阅读本计划，并以 A2 v1 源码、pair、开发/held-out 结果为冻结输入；不得用 I1 held-out 结果回调碰撞参数。

### 2026-08-06 — I2 Contact-GMR 开始

- 已按执行规则重新阅读全文；I2 状态更新为 `in_progress`。I0/I1 源码、参数、pair、开发与 held-out 结果全部冻结，不允许依据 A3 结果回调。
- A3 必须直接继承冻结 A2 Collision-GMR v1，只新增人体接触推断、机器人足底保持与根高度穿透修正；原 GMR、质量评价项目和既有 A0/A1/A2 输出保持只读。
- 开发仍限于 Step-10 的 15 条、90,540 帧；只有 A3 开发候选通过预注册门控并锁定后，才可使用既有 15 条、91,627 帧 held-out。
- 当前先只读核对 LAFAN1 人体足部位置/速度字段、G1 足部 frame/geom、`feet_only` 与 `floor_motion` 评价语义、A2 穿地/脚滑失败分布及 Mink frame task 契约；在读取任何 A3 输出前锁定接触阈值、迟滞、足底 anchor、根高度修正和验收指标。
- 当前下一动作：完成上述契约审计并写入机器可读预注册配置；此时不得以 A3 冒烟效果选择参数。

### 2026-08-06 16:04 CST — I2 接触语义与 v1 参数冻结

- 代码契约确认：LAFAN1 loader 提供 `LeftFootMod/RightFootMod` 的世界位置；G1 每只 `ankle_roll_link` 下有 4 个半径 5 mm 的 sole sphere；冻结评价器也用这 8 个 sphere 的最低点、水平/竖直速度计算接触代理和脚滑。
- A3 v1 将人体接触推断与机器人修正分开：源足高度以整条 BVH 双足高度 2% 分位为地面，进入/退出高度为 4/6 cm，竖直和水平速度迟滞均为 `0.2/0.4 m/s`；差分只使用当前与前一帧，因此标签可因果在线计算，地面估计为序列级预处理。
- `feet_only` 接触段增加足 body 世界位置 anchor，xy/z cost=`100/50`；根高度修正读取 MuJoCo 全 body-ground contact 的最大深度，以残余 5 mm 为目标，每帧上升/释放最多 20/5 mm、单帧额外上移最多 50 mm。修正只改变 floating root z，不绕过 A2 关节速度信赖域。
- `floor_motion` 使用独立语义策略：人体接触标签、足 anchor 和根上移全部禁用，并要求 A3 与冻结 A2 PKL 逐元素完全一致；不把合理的躯干/四肢触地当成应消除接触。
- 在生成任何 A3 输出前完成源输入审计：15 条、90,540 帧；12 条 `feet_only` 有 58,647 帧至少一脚接触（77.25%），3 条 `floor_motion` 接触标签严格为 0。该结果只验证输入标签非退化，不是 A3 效果证据。输入审计 SHA-256=`9cfc9b1c...c779`。
- 开发配置 `configs/contact_gmr_v1.yaml` SHA-256=`bc33536e...6254`。预注册主门控限定 `feet_only`：脚滑帧率与穿地帧率严格下降，严重穿地与非预期触地不增加；另要求 floor-motion exact no-op、无新增 hard-fail、总体 fidelity 相对 A2 下降不超过 0.02、突跳/速度超限维持 0、自碰撞帧率增加不超过 0.001。
- 当前下一动作：只做不改变上述参数的实现冒烟和不变量修复；随后冻结最终源码哈希，在新目录运行完整开发集。

### 2026-08-06 16:32 CST — I2 工程冒烟、首帧锚点修复与源码冻结

- 完成 `ContactGeneralMotionRetargeting`、正式运行器、源接触输入审计、A2/A3 配对比较器及不变量测试；Contact v1 参数和预注册验收门槛均未改变。
- 首次 `walk2_subject1` 300 帧冒烟保留于 `outputs/contact_gmr_smoke_feet_v1`：足锚点在人体/机器人首帧对齐前的中立姿态建立，导致左右足锚点误差 p95/max 达约 `0.378/0.379 m` 与 `0.286/0.379 m`。这是实现时序错误而非参数效果，不能作为 Contact-GMR 性能结果。
- 修复仅将首次 anchor 建立延后到首个已对齐输出帧；修复后同一前缀保留于 `outputs/contact_gmr_smoke_feet_v2`，299 个 anchor frame 的左右足误差 p95 约 `0.021/0.026 m`、最大值约 `0.041/0.048 m`。`ground1_subject1` 300 帧冒烟保持 anchor/root correction 全禁用，并与冻结 A2 逐元素一致。
- 短前缀冻结质量指标的脚滑/穿地代理均为 0，不能用于证明改善；同时 A3 root jerk p95 高于 A2（约 `163.22` 对 `97.21`），作为潜在根高度时序副作用保留，必须由完整开发集原样检验。
- 冻结实现哈希：`contact.py=8c57d5e1...e15`、runner=`2b65a0d8...9ed5`、CLI=`8ed9077c...d54`、比较器=`f0ebc634...d92a`；开发配置最终 SHA-256=`679d6d35...779`。源接触输入审计仍为 `9cfc9b1c...c779`，参数未改。
- 全项目 `pytest` 为 44 passed，Contact 相关编译检查通过。当前下一动作：向新的正式目录生成完整 15 条、90,540 帧 A3，并只用冻结质量评价器与 A2 做预注册配对比较；正式结果出现后不得调参覆盖 v1。

### 2026-08-06 16:55 CST — I2 Contact v1 正式开发门控未通过

- 冻结 A3 v1 完成开发集 15 条、90,540 帧生成，运行 manifest 标记 `complete=true/formal_run=true`；3 条 `floor_motion` 均为 anchor=0、root correction=0，且相对 A2 的 `root_pos/root_rot/dof_pos` 最大绝对差严格为 0。
- 冻结评价器 15/15 成功、fidelity 15/15 为 `enabled_verified`。A2/A3 hard-fail 数为 `12 -> 11`，无新增 hard-fail；突跳率和速度超限率保持 0。
- 预注册 `feet_only` 四项接触指标全部改善：脚滑帧率 `0.02153554 -> 0.01577956`（`-0.00575598`），穿地帧率 `0.02596120 -> 0.00352999`（`-0.02243121`），严重穿地 `0.00561110 -> 0.00172548`，非预期触地 `0.01139342 -> 0.00886448`。
- 自碰撞保持门控通过：总体非手部自碰撞帧率增加 `0.00059642`，小于上限 `0.001`。但总体 fidelity pass rate `0.86497681 -> 0.84375966`，下降 `0.02121714`，超过预注册上限 `0.02`，因此 `contact_gate_pass=false`。
- root jerk p95 总体由约 `393.19 -> 438.83 m/s^3`，与冒烟阶段观察到的根高度时序副作用方向一致；这只是归因线索，尚需逐动作和逐帧诊断审计。
- 根据预注册规则不放宽阈值、不覆盖 v1，也不解封 held-out。当前下一动作：完成逐动作失败归因、根修正/anchor 不变量审计和开发阶段负结果报告；若提出 v2，必须作为新的、显式预注册候选，不能把 v1 伪装成通过。

### 2026-08-06 17:14 CST — I2 v1 审计完成与 v2 单因素预注册

- 独立审计 `data/contact_gmr_development_v1_audit.json` 结果 `ok=true`：15 条、90,540 帧、文件/源码 0 mismatch、Contact 逐帧不变量 0 failure；SHA-256=`8f6390ff...2812`。
- `feet_only` 共 75,921 帧：人体接触 58,647 帧、anchor 活跃 58,636 帧、根修正 2,735 帧、root lift clipped 846 帧。修正后穿透 p99 为 5 mm，但最大仍为 `0.16065 m`，故 v1 不能宣称消除全部穿透。
- fidelity 逐帧配对为 lost 2,355、gained 434、净损失 1,921；lost 中 2,335 帧 anchor 活跃、103 帧直接 root lift，2,246 帧越过冻结 0.1 m key-body 位置阈值。`walk4_subject1` 与 `walk1_subject1` 分别净损失 753/423 帧，共占净损失 61.2%。
- 正式负结果报告为 `reports/CONTACT_GMR_V1_DEVELOPMENT_REPORT.md`。相关性仅作为开发线索：12 条 `feet_only` 中 anchor 暴露率与 fidelity delta 的 Pearson/Spearman 约 `-0.732/-0.839`，不写成因果结论。
- 在生成任何 v2 A3 输出前预注册唯一变化：anchor xy/z cost 从 `100/50` 同比例减半至 `50/25`。理由是 v1 接触/穿透收益已成立，而 fidelity 损失主要暴露于长期 anchor；保持 cost 比例并只做一次 0.5 松弛，避免多参数搜索。
- v2 的接触阈值、迟滞、sole clearance、根修正目标/上限/上升/释放、A2 父方法、开发 cohort、质量配置和全部验收门槛逐项保持 v1 不变。v2 必须写入新 config/assets/output；若仍失败则不再在同一开发集继续调 anchor cost，也不运行 held-out。
- 当前下一动作：生成与 v2 参数精确匹配的 source-contact 输入审计和冻结配置，完成短冒烟不变量后运行完整 v2 development；不得删除或覆盖 v1。

### 2026-08-06 17:22 CST — I2 v2 输入/config 冻结与工程冒烟

- 新 source-only 审计 `assets/contact_gmr_v2/contact_input_audit.json` 精确记录 xy/z cost=`50/25`，其余参数与 v1 相同；SHA-256=`af13a446...d89d8`。标签 CSV 与 v1 逐字节一致，SHA-256 均为 `20c548e0...4c00`，确认 v2 没有暗改接触标签。
- v2 正式开发配置 `configs/contact_gmr_v2.yaml` SHA-256=`b16d9b04...cb56`；冻结 GMR/A1/A2/Contact 源码、模型、pair、质量配置和 15 条/90,540 帧 cohort 哈希全部由运行器冒烟校验通过。
- `walk4_subject1` 300 帧工程冒烟完成：299 帧 anchor 活跃、0 帧 root correction、信赖域最大占用比约 `0.815`；v2 anchor error p95/max 约 `0.0674/0.1076 m`，高于 v1 同前缀的 `0.0339/0.0590 m`，符合降低软约束后的预期方向，但不是质量改善证据。
- 当前下一动作：向新目录运行完整 v2 development 并使用同一冻结评价/门控；正式结果后不得再次在该开发集调 anchor cost。

### 2026-08-06 17:48 CST — I2 v2 开发门控通过，held-out 解封

- v2 完成开发集 15 条、90,540 帧生成与冻结质量评价；15/15 成功、fidelity 全部 `enabled_verified`。3 条 `floor_motion` 逐元素 no-op，突跳/速度超限维持 0，无新增 hard-fail，hard-fail 数 `12 -> 10`。
- 预注册 `feet_only` 结果：脚滑帧率 `0.02153554 -> 0.01770261`（`-0.00383293`），穿地 `0.02596120 -> 0.00363536`（`-0.02232584`），严重穿地 `0.00561110 -> 0.00179134`，非预期触地 `0.01139342 -> 0.00887765`，四项门控均通过。
- 总体 fidelity `0.86497681 -> 0.86246963`，下降 `0.00250718 < 0.02`；非手部自碰撞帧率下降 `0.00068478`。总体 root jerk p95 仍增加约 `11.16 m/s^3`，作为副作用保留但不触发已冻结门控。
- v2 独立审计 `data/contact_gmr_development_v2_audit.json`：`ok=true`、15 条/90,540 帧、0 integrity mismatch、0 Contact invariant failure；SHA-256=`b50e7e87...946e`。生成/质量/比较 summary manifest 哈希分别为 `c91789a4...bfee`、`ad01e35d...9e23`、`d8e4e3b1...96c5`。
- v2 通过开发门控，因此现在只解封 I0 前已固定的 held-out 15 条、91,627 帧；anchor cost 与所有其他参数锁定，不得依据 held-out 回调。
- 当前下一动作：在任何 A3 held-out 输出前，针对冻结 A2 held-out catalog 生成 source-contact 输入审计并写入 held-out v2 配置；随后向全新目录完整生成和评价。

### 2026-08-06 17:55 CST — I2 held-out 输入与配置冻结

- 在生成任何 A3 held-out 输出前完成源接触审计：15 条、91,627 帧；12 条 `feet_only` 有 53,645 帧至少一脚接触（69.78%），3 条 `floor_motion` 标签严格为 0。审计 SHA-256=`6ac0c933...f9e7`，输入 A2 catalog SHA-256=`8b6eb9a4...bc68`。
- 正式 held-out 配置 `configs/contact_gmr_heldout_v2.yaml` SHA-256=`5faeb5ab...37b9`，锁定 v2 anchor cost=`50/25`、全部其他 v1 参数、Contact/A1/A2 源码、碰撞模型/pair、质量配置以及 15 条/91,627 帧输入。
- source catalog 与 A2 reference catalog 均指向冻结 A2 held-out catalog；`floor_motion` 将再次由运行器逐元素验证，不依赖文件名或口头假设。
- 当前尚未生成或读取任何 A3 held-out 指标。下一动作：向新的 `outputs/contact_gmr_heldout_v2` 完整生成；参数和验收门槛不得依据结果更改。

### 2026-08-06 18:20 CST — I2 held-out 验证与最终交付完成

- 冻结 v2 在独立 held-out 15 条、91,627 帧上完整生成；质量评价 15/15 成功、fidelity 全部 `enabled_verified`，3 条 `floor_motion` 相对 A2 逐元素差严格为 0。
- held-out `feet_only`：脚滑帧率 `0.02027862 -> 0.01611623`，穿地 `0.04341888 -> 0.00543712`，严重穿地 `0.00725816 -> 0.00120969`，非预期触地 `0.03199834 -> 0.02967000`。四项 motion-level bootstrap 平均差的 95% CI 均完全小于 0。
- 总体 fidelity pass rate 下降 `0.00399446 < 0.02`；非手部自碰撞帧率增加 `0.00032741 < 0.001`；hard-fail `12 -> 11` 且无新增；突跳/速度超限维持 0。正式 `contact_gate_pass=true`。
- held-out 独立审计 `data/contact_gmr_heldout_v2_audit.json` 为 15 条/91,627 帧、0 integrity mismatch、0 Contact invariant failure；SHA-256=`bcee3c1b...ee2e`。
- 原样保留反例/副作用：最大修正后穿透仍为 `0.07078 m`；root jerk p95 增加 `24.69 m/s^3`；自碰撞事件 `488 -> 501`；`walk3_subject3` 自碰撞率增加约 `0.00460` 且 root jerk 增加约 `143.89 m/s^3`；`dance1_subject2` 脚滑率增加约 `0.00330`。
- 最终报告 `reports/CONTACT_GMR_I2_FINAL_REPORT.md` SHA-256=`df30ca98...04bb8`；生成 4 个不覆盖正式 PKL 的 A2/A3 viewer 兼容副本，用于复核 `walk3_subject3` 与 `dance1_subject2`。
- 全项目 `pytest`：54 passed；`compileall` 通过；`pip check`：No broken requirements found。I2 交付 manifest SHA-256=`75803e23...20c7c`，最终审计 `ok=true`、46/46 文件、0 mismatch，审计 SHA-256=`31b34ea9...d6b4`。
- GMR 与质量评价项目全程只读；未使用未校准综合分数。I2 状态更新为 `completed`。下一阶段应固定 A2/A3 v2 数据做同协议仿真 tracking/任务与模仿学习验证，不得继续用本 held-out 回调 Contact 参数。
