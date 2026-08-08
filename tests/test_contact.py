from __future__ import annotations

import numpy as np
import pytest

from gmr_improved.contact import (
    ContactGMRConfig,
    _infer_one_foot,
    infer_human_contact_sequence,
)


def test_contact_hysteresis_uses_separate_enter_and_exit_thresholds() -> None:
    config = ContactGMRConfig()
    heights = np.array([0.03, 0.05, 0.061, 0.03])
    speed = np.zeros(4)
    states, transitions = _infer_one_foot(heights, speed, speed, config)
    assert states.tolist() == [True, True, False, True]
    assert transitions == ("enter", "stay_contact", "exit", "enter")


def test_speed_exits_contact_and_requires_enter_speed_to_reenter() -> None:
    config = ContactGMRConfig()
    heights = np.full(4, 0.01)
    vertical = np.array([0.0, 0.41, 0.21, 0.19])
    horizontal = np.zeros(4)
    states, _ = _infer_one_foot(heights, vertical, horizontal, config)
    assert states.tolist() == [True, False, False, True]


def test_floor_motion_contact_inference_is_semantic_noop() -> None:
    config = ContactGMRConfig()
    frame = {
        "LeftFootMod": [np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0, 0.0])],
        "RightFootMod": [np.array([0.0, 0.1, 0.0]), np.array([1.0, 0.0, 0.0, 0.0])],
    }
    result = infer_human_contact_sequence([frame, frame], 30.0, "floor_motion", config)
    assert all(not item.left_contact and not item.right_contact for item in result.frames)


def test_contact_config_rejects_floor_motion_intervention() -> None:
    with pytest.raises(ValueError, match="semantic no-op"):
        ContactGMRConfig(enable_floor_motion_root_lift=True)


def test_first_frame_anchor_initialization_is_documented_as_deferred() -> None:
    # Regression marker for the neutral-world anchor bug: the implementation
    # must keep the explicit first-output guard.
    import inspect

    from gmr_improved.contact import ContactGeneralMotionRetargeting

    source = inspect.getsource(ContactGeneralMotionRetargeting._prepare_anchors)
    assert "self.previous_output_qpos is None" in source
