# I0 测试可视化指南

## 直接查看

- `01_test_completion_dashboard.png`：先看测试流水线是否全部完成，以及 held-out 门控是否通过。
- `02_overall_metrics_a0_a1.png`：看总体主指标和碰撞/接触副作用。
- `03_category_improvement_heatmap.png`：正值表示改善，可定位哪类动作获益或退化。
- `04_motion_tradeoff.png`：每个点是一条动作，横轴越右代表速度改善越多，纵轴越低代表 fidelity 损失越大。
- `05_dance1_subject2_timeline.png`：查看最明显 trade-off 动作的逐帧速度、fidelity 和近限位变化。

可以直接打开 `index.html`，或在本目录运行：

```bash
python -m http.server 8000
```

然后浏览器访问 `http://127.0.0.1:8000/`。

## MuJoCo 动作回放

A0：

```bash
conda run -n gmr python /root/gpufree-data/GMR/scripts/vis_robot_motion.py \
  --robot unitree_g1 \
  --robot_motion_path /root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a0_v1/retargeted/dance1_subject2.pkl
```

A1：把路径改为：

```text
/root/gpufree-data/gmr_improved/outputs/temporal_gmr_heldout_a1_v1/retargeted/dance1_subject2.pkl
```

该回放需要图形桌面；无桌面环境时使用上述静态图。A0/A1 最好分别录屏后并排比较，不要仅凭单次肉眼印象替代基础指标。
