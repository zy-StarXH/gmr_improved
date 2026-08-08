from __future__ import annotations

import contextlib
import io
from pathlib import Path

import mink
import numpy as np
import pytest

from gmr_improved.collision import (
    CollisionGMRConfig,
    CollisionGeneralMotionRetargeting,
    DeterministicCollisionAvoidanceLimit,
    load_audited_geom_pairs,
)
from gmr_improved.temporal import TemporalGMRConfig


ASSET = Path("/root/gpufree-data/gmr_improved/assets/collision_g1_v1")
DERIVED_XML = ASSET / "g1_mocap_29dof_collision_named.xml"
PAIR_CSV = ASSET / "collision_pairs.csv"


def _build_retargeter() -> CollisionGeneralMotionRetargeting:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        return CollisionGeneralMotionRetargeting(
            src_human="bvh_lafan1",
            tgt_robot="unitree_g1",
            actual_human_height=1.75,
            solver="daqp",
            damping=0.5,
            verbose=False,
            temporal_config=TemporalGMRConfig(
                max_joint_velocity_rad_s=9.41535318280861
            ),
            collision_config=CollisionGMRConfig(),
            derived_robot_xml=DERIVED_XML,
            collision_pairs_csv=PAIR_CSV,
        )


def test_collision_retargeter_uses_named_model_and_audited_pairs() -> None:
    from general_motion_retargeting.params import ROBOT_XML_DICT

    original = ROBOT_XML_DICT["unitree_g1"]
    retargeter = _build_retargeter()
    assert ROBOT_XML_DICT["unitree_g1"] == original
    assert Path(retargeter.xml_file).resolve() == DERIVED_XML.resolve()
    assert len(retargeter.audited_geom_id_pairs) == 362
    assert isinstance(retargeter.collision_limit, DeterministicCollisionAvoidanceLimit)
    assert retargeter.ik_limits[-1] is retargeter.collision_limit
    constraint = retargeter.collision_limit.compute_qp_inequalities(
        retargeter.configuration, dt=retargeter.model.opt.timestep
    )
    assert constraint.G is not None and constraint.G.shape == (362, 35)
    assert constraint.h is not None and constraint.h.shape == (362,)
    assert np.isfinite(constraint.G).all()


def test_collision_short_prefix_keeps_temporal_budget_and_diagnostics_aligned() -> None:
    from general_motion_retargeting.utils.lafan1 import load_bvh_file

    frames, _ = load_bvh_file(
        "/root/gpufree-data/ubisoft-laforge-animation-dataset/lafan1/datasets/walk1_subject1.bvh",
        format="lafan1",
    )
    retargeter = _build_retargeter()
    outputs = [retargeter.retarget(frame) for frame in frames[:3]]
    assert len(retargeter.frame_diagnostics) == 3
    assert len(retargeter.collision_frame_diagnostics) == 3
    assert all(item.audited_pair_count == 362 for item in retargeter.collision_frame_diagnostics)
    step = retargeter.frame_velocity_limit.displacement_from_reference(outputs[-1])
    assert np.max(np.abs(step)) <= np.max(retargeter.frame_velocity_limit.budget) + 1e-7
    assert retargeter.frame_diagnostics[-1].max_abs_joint_step_rad == pytest.approx(
        np.max(np.abs(step))
    )
    assert retargeter.frame_diagnostics[-1].max_trust_region_ratio <= 1.0 + 1e-6


def test_runtime_pair_loader_reconstructs_frozen_order() -> None:
    model = mink.Configuration(
        __import__("mujoco").MjModel.from_xml_path(str(DERIVED_XML))
    ).model
    pairs = load_audited_geom_pairs(PAIR_CSV, model, CollisionGMRConfig())
    assert len(pairs) == 362
    assert list(pairs) == sorted(pairs)
