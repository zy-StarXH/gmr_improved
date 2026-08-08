from __future__ import annotations

from gmr_improved.i2_delivery import DELIVERY_ARTIFACTS, FROZEN_HASHES


def test_i2_delivery_artifacts_are_unique() -> None:
    assert len(DELIVERY_ARTIFACTS) == len(set(DELIVERY_ARTIFACTS))


def test_i2_frozen_hashes_are_complete_sha256() -> None:
    assert FROZEN_HASHES
    assert all(len(value) == 64 for value in FROZEN_HASHES.values())
