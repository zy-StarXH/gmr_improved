from __future__ import annotations

import numpy as np

from gmr_improved.collision_geometry_audit import _count_rising_edges


def test_rising_edges_count_pair_events_independently() -> None:
    previous = np.array([False, True, False, True])
    current = np.array([True, True, False, False])
    assert _count_rising_edges(current, previous) == 1
