# gmr_improved

本项目用于在不修改原始 GMR 与质量评价项目的前提下，复现并分析 GMR 的失败案例，随后实施可消融的渐进约束改进。

首要入口是 [`PLAN.md`](PLAN.md)。任何任务都必须先阅读并更新计划。

冻结基线分析：

```bash
cd /root/gpufree-data/gmr_improved
conda run -n gmr python -m gmr_improved analyze-baseline \
  --config configs/baseline_analysis.yaml \
  --output-dir outputs/<new_empty_output_dir> \
  --json
```

该命令只使用基础逐帧指标、事件和来源元数据，不读取未校准综合分数作为分析依据。

第 3 步正式结论见 [`reports/GMR_FAILURE_ANALYSIS.md`](reports/GMR_FAILURE_ANALYSIS.md)，冻结案例与视觉复核见 [`reports/FAILURE_CASE_CATALOG_v2.csv`](reports/FAILURE_CASE_CATALOG_v2.csv)。正式机器输出为 `outputs/baseline_failure_analysis_v2`。

Temporal-GMR I0 的冻结候选为 `configs/temporal_gmr_v2.yaml`。开发过程见 [`reports/TEMPORAL_GMR_REPORT.md`](reports/TEMPORAL_GMR_REPORT.md)，预注册独立测试与最终结论见 [`reports/TEMPORAL_GMR_I0_FINAL_REPORT.md`](reports/TEMPORAL_GMR_I0_FINAL_REPORT.md)。运行入口为：

```bash
cd /root/gpufree-data/gmr_improved
PYTHONPATH=src conda run -n gmr python -m gmr_improved.temporal_cli \
  --config configs/temporal_gmr_v2.yaml \
  --output-dir outputs/<new_empty_output_dir>
```

该命令不会修改 GMR。`v1` 的速度上界恰好等于评价阈值，保留为浮点边界负结果；`v2` 使用 0.1% 数值安全余量。

I0 已在独立留出集的 15 条、91,627 帧上通过预注册门控。最终可视化入口为 [`outputs/temporal_gmr_heldout_visualization_v3/index.html`](outputs/temporal_gmr_heldout_visualization_v3/index.html)，使用方法见同目录的 [`VISUALIZATION_GUIDE.md`](outputs/temporal_gmr_heldout_visualization_v3/VISUALIZATION_GUIDE.md)。该结果不等于下游机器人学习实验已经完成。

Collision-GMR I1 已在冻结 Temporal-GMR v2 上加入经过 pair 审计的非相邻碰撞约束。正式实现配置为 [`configs/collision_gmr_heldout_v1.yaml`](configs/collision_gmr_heldout_v1.yaml)，完整方法、开发/留出结果、负结果和 MuJoCo 回放命令见 [`reports/COLLISION_GMR_I1_FINAL_REPORT.md`](reports/COLLISION_GMR_I1_FINAL_REPORT.md)。运行入口为：

```bash
cd /root/gpufree-data/gmr_improved
PYTHONPATH=src conda run -n gmr python -m gmr_improved.collision_cli \
  --config configs/collision_gmr_heldout_v1.yaml \
  --output-dir outputs/<new_empty_output_dir>
```

I1 在独立留出集上降低了非手部碰撞帧率和事件数，但没有保证每帧严格无穿透；12/15 hard-fail 数量也未下降。该边界是正式结果的一部分。
