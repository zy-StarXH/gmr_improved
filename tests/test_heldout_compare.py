import pandas as pd
import pytest

from gmr_improved.heldout_compare import _weighted_metric


def test_heldout_derivative_rate_uses_interval_weights() -> None:
    frame = pd.DataFrame(
        {"num_frames": [2, 4], "joint_jump_rate": [1.0, 0.0]}
    )
    assert _weighted_metric(frame, "joint_jump_rate") == pytest.approx(0.25)


def test_heldout_fidelity_uses_aligned_frame_weights() -> None:
    frame = pd.DataFrame(
        {
            "fidelity_aligned_frame_count": [1, 3],
            "fidelity_pass_frame_rate": [1.0, 0.0],
        }
    )
    assert _weighted_metric(frame, "fidelity_pass_frame_rate") == pytest.approx(0.25)

