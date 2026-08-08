from __future__ import annotations

import pandas as pd
import pytest

from gmr_improved.contact_compare import _aggregate, _weighted_rate


def test_contact_rate_uses_frame_weighting() -> None:
    frame = pd.DataFrame({"num_frames": [2, 8], "foot_slide_frame_rate": [1.0, 0.0]})
    assert _weighted_rate(frame, "foot_slide_frame_rate") == pytest.approx(0.2)


def test_contact_counts_are_summed() -> None:
    frame = pd.DataFrame({"foot_slide_frame_count": [2, 3]})
    assert _aggregate(frame, "foot_slide_frame_count") == 5.0
