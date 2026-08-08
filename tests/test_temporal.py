from __future__ import annotations

import contextlib
import io
from pathlib import Path

import mink
import mujoco
import numpy as np
import pytest

from gmr_improved.temporal import (
    SoftJointLimitTask,
    TemporalGMRConfig,
    TemporalGeneralMotionRetargeting,
    WholeFrameVelocityLimit,
)


PROJECT = Path(__file__).resolve().parents[1]
GMR_ROOT = Path("/root/gpufree-data/GMR")


def _one_joint_model() -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_string(
        """
        <mujoco>
          <compiler angle="radian"/>
          <option timestep="0.002"/>
          <worldbody>
            <body name="link">
              <joint name="joint" type="hinge" range="-1 1" limited="true"/>
              <geom type="capsule" size="0.02 0.1"/>
            </body>
          </worldbody>
        </mujoco>
        """
    )


def test_whole_frame_limit_tracks_remaining_budget_across_substeps() -> None:
    model = _one_joint_model()
    configuration = mink.Configuration(model)
    limit = WholeFrameVelocityLimit(model, max_velocity=2.0, frame_dt=0.1)
    limit.set_reference(np.array([0.0]))
    configuration.update(np.array([0.12]))
    constraint = limit.compute_qp_inequalities(configuration, dt=0.002)
    assert constraint.h is not None
    np.testing.assert_allclose(constraint.h, [0.08, 0.32])


def test_repeated_ik_solves_share_one_frame_budget() -> None:
    model = _one_joint_model()
    configuration = mink.Configuration(model)
    target = mink.PostureTask(model, cost=1.0)
    target.set_target(np.array([0.9]))
    limit = WholeFrameVelocityLimit(model, max_velocity=2.0, frame_dt=0.1)
    limit.set_reference(configuration.q.copy())
    for _ in range(6):
        velocity = mink.solve_ik(
            configuration,
            [target],
            dt=0.002,
            solver="daqp",
            limits=[mink.ConfigurationLimit(model), limit],
        )
        configuration.integrate_inplace(velocity, 0.002)
    assert configuration.q[0] <= 0.2 + 1e-7
    assert configuration.q[0] == pytest.approx(0.2, abs=1e-7)


def test_soft_limit_task_is_inactive_interior_and_points_inward() -> None:
    model = _one_joint_model()
    configuration = mink.Configuration(model)
    task = SoftJointLimitTask(model, cost=3.0, margin_fraction=0.1)
    configuration.update(np.array([0.0]))
    np.testing.assert_array_equal(task.compute_jacobian(configuration), np.zeros((1, 1)))
    configuration.update(np.array([0.95]))
    assert task.compute_error(configuration)[0] == pytest.approx(0.15)
    assert task.compute_jacobian(configuration)[0, 0] == 1.0
    assert task.active_joint_names(configuration) == ("joint",)


def test_temporal_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="output_fps"):
        TemporalGMRConfig(output_fps=0.0)
    with pytest.raises(ValueError, match="soft_limit_margin_fraction"):
        TemporalGMRConfig(soft_limit_margin_fraction=0.5)


def test_disabled_temporal_retargeter_is_exact_a0_for_short_prefix() -> None:
    from general_motion_retargeting import GeneralMotionRetargeting
    from general_motion_retargeting.utils.lafan1 import load_bvh_file

    bvh = Path(
        "/root/gpufree-data/ubisoft-laforge-animation-dataset/lafan1/datasets/walk1_subject1.bvh"
    )
    frames, height = load_bvh_file(str(bvh), format="lafan1")
    captured = io.StringIO()
    kwargs = dict(
        src_human="bvh_lafan1",
        tgt_robot="unitree_g1",
        actual_human_height=height,
        solver="daqp",
        damping=0.5,
        verbose=False,
        use_velocity_limit=False,
    )
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        baseline = GeneralMotionRetargeting(**kwargs)
        temporal_disabled = TemporalGeneralMotionRetargeting(
            **kwargs, temporal_config=TemporalGMRConfig(enabled=False)
        )
    for frame in frames[:3]:
        expected = baseline.retarget(frame)
        actual = temporal_disabled.retarget(frame)
        np.testing.assert_array_equal(actual, expected)
