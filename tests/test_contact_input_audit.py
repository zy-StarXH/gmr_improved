from __future__ import annotations

import pytest

from gmr_improved.contact import ContactGMRConfig
from gmr_improved.contact_input_audit_cli import main


def test_default_input_audit_parameters_match_preregistration() -> None:
    config = ContactGMRConfig()
    assert config.ground_percentile == 2.0
    assert config.enter_height_m == 0.04
    assert config.exit_height_m == 0.06
    assert config.enable_feet_only_anchors
    assert not config.enable_floor_motion_anchors


def test_cli_requires_anchor_cost_pair(tmp_path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--catalog",
                str(tmp_path / "catalog.csv"),
                "--output-dir",
                str(tmp_path / "output"),
                "--anchor-xy-cost",
                "50",
            ]
        )
