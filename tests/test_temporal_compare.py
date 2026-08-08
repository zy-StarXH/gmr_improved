from __future__ import annotations

import pandas as pd
import pytest

from gmr_improved.temporal_compare import _bool_series, _weighted_rate


def test_derivative_rate_uses_t_minus_one_weight() -> None:
    frame = pd.DataFrame(
        {"num_frames": [2, 4], "joint_jump_rate": [1.0, 0.0]}
    )
    assert _weighted_rate(frame, "joint_jump_rate") == pytest.approx(0.25)


def test_boolean_parser_is_strict() -> None:
    assert _bool_series(pd.Series(["true", "false"])).tolist() == [True, False]
    with pytest.raises(ValueError, match="Invalid boolean"):
        _bool_series(pd.Series(["yes"]))

