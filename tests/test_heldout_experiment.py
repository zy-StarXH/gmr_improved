from pathlib import Path

import pandas as pd
import pytest

from gmr_improved.heldout_experiment import load_heldout_config, sha256_file


PROJECT = Path(__file__).resolve().parents[1]


def test_heldout_catalog_is_frozen_balanced_and_disjoint() -> None:
    config = load_heldout_config(PROJECT / "configs" / "temporal_gmr_heldout_v1.yaml")
    catalog = pd.read_csv(config["paths"]["source_catalog"])
    development = pd.read_csv(
        "/root/gpufree-data/retargeting_quality_assessment/outputs/step10_dataset/step10_motion_catalog.csv"
    )
    assert len(catalog) == 15
    assert int(catalog["source_frame_count"].sum()) == 91627
    assert set(catalog["motion_name"]).isdisjoint(development["motion_name"])
    assert catalog["motion_category"].value_counts().to_dict() == {
        "standing_walking": 3,
        "running_jumping": 3,
        "dance": 3,
        "complex_dynamic": 3,
        "floor_motion": 3,
    }
    assert set(catalog["selection_status"]) == {"preregistered_heldout"}
    assert sha256_file(config["paths"]["source_catalog"]) == (
        config["frozen_hashes"]["source_catalog_sha256"]
    )


def test_heldout_temporal_parameters_equal_frozen_v2() -> None:
    config = load_heldout_config(PROJECT / "configs" / "temporal_gmr_heldout_v1.yaml")
    assert config["_temporal_config"].max_joint_velocity_rad_s == pytest.approx(
        9.41535318280861
    )
    assert sha256_file(config["paths"]["frozen_temporal_implementation"]) == (
        config["frozen_hashes"]["frozen_temporal_implementation_sha256"]
    )

