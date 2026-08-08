from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gmr_improved.collision_compare import (
    _aggregate,
    _bool_series,
    _bootstrap_mean_delta,
    _weighted_rate,
)


def test_collision_rate_uses_frame_weighting() -> None:
    frame = pd.DataFrame(
        {"num_frames": [2, 8], "self_collision_nonhand_frame_rate": [1.0, 0.0]}
    )
    assert _weighted_rate(frame, "self_collision_nonhand_frame_rate") == pytest.approx(0.2)


def test_event_counts_are_summed() -> None:
    frame = pd.DataFrame({"self_collision_nonhand_event_count": [2, 3]})
    assert _aggregate(frame, "self_collision_nonhand_event_count") == 5.0


def test_boolean_parser_is_strict() -> None:
    assert _bool_series(pd.Series([True, False])).tolist() == [True, False]
    with pytest.raises(ValueError, match="Invalid boolean"):
        _bool_series(pd.Series(["pass"]))


def test_bootstrap_is_deterministic() -> None:
    values = np.array([-1.0, 0.0, 1.0])
    assert _bootstrap_mean_delta(values) == _bootstrap_mean_delta(values)
