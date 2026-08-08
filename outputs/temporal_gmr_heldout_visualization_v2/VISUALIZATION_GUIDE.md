# I0 测试可视化指南

查看顺序：

1. `01_test_completion_dashboard.png`：确认冻结输入、A0/A1 生成、质量评估、配对门控和核心审计全部 PASS。
2. `02_overall_metrics_a0_a1.png`：比较总体主指标及碰撞/接触副作用。
3. `03_category_improvement_heatmap.png`：正值为改善，负值为退化。
4. `04_motion_tradeoff.png`：横轴越右表示速度改善越多；纵轴越低表示 fidelity 损失越大。
5. `05_dance1_subject2_timeline.png`：检查代表性高速动作的逐帧约束效果。

浏览器汇总：

```bash
cd /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_visualization_v2
python -m http.server 8000
```

访问 `http://127.0.0.1:8000/`。

MuJoCo 回放 A0：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a0_v1/retargeted/dance1_subject2.pkl
```

回放 A1 时把目录改为 `temporal_gmr_heldout_a1_v1/retargeted`。GUI 回放需要图形桌面；建议 A0/A1 分别录屏并排观察，不能用肉眼回放替代定量门控。
