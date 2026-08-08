# 冻结失败窗口结构化视觉复核协议

本协议用于核对基础指标定位的局部异常是否能在 Unitree G1 静态 FK 姿态和同窗口时间线中得到支持。它不评价控制器能否跟踪，也不证明动力学可执行性。

## 冻结抽样

- 候选由 `analyze-baseline` 在任何局部图被查看前固定；
- 自碰撞、穿地、突跳分别按事件最大严重度、持续时间、motion name 排序，并在同类中优先选择不同动作；
- 另含两个预注册、无 Step 10 hard-fail 的对照动作；
- 每个窗口在事件前后各扩展 1 秒，姿态图均匀固定 5 帧，不允许人工换帧。

## 复核输入

- `cases/Cxx/pose_montage.png`：锁定 G1 XML 的 MuJoCo FK 骨架，不显示实体碰撞 mesh；
- `cases/Cxx/metric_timeline.png`：关节 step、速度、最小限位余量、穿透深度和非手部自碰撞布尔量；
- `tables/failure_case_catalog.csv`：事件实体、持续时间与最大严重度；
- `tables/collision_pair_hotspots.csv`：碰撞 pair 的运动学树距离，用于提示相邻/近相邻几何固有重叠风险。

## 字段

- `visible_artifact`：`confirmed`、`partial`、`likely_metric_artifact`、`uncertain` 或 `control_plausible`；
- `metric_agreement`：`agree`、`partial`、`disagree` 或 `not_applicable`；
- `notes`：同时记录视觉、数值和语义限制；
- `reviewer`、`reviewed_at`：记录复核主体和日期。

骨架点线图不显示 mesh 体积，因此“未直接看见相交”不能推翻 MuJoCo 几何距离；floor motion 的贴地语义也不能反向证明 5–20 cm 的几何穿透合理。两类证据冲突时必须记录为 `partial` 或 `uncertain`。

