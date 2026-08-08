from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from gmr_improved.analysis import (
    _as_bool,
    finalize_visual_review,
    _metric_masks,
    _motion_summary,
    _overlap_table,
    load_config,
    verify_manifest,
)


PROJECT = Path(__file__).resolve().parents[1]


def test_frozen_config_contract() -> None:
    config = load_config(PROJECT / "configs" / "baseline_analysis.yaml")
    assert config["expected"]["motion_count"] == 15
    assert config["expected"]["total_frames"] == 90540
    assert config["research_boundary"]["use_quality_score"] is False
    assert sum(config["analysis"]["case_counts"].values()) + len(
        config["analysis"]["controls"]
    ) == 12


def test_boolean_parser_rejects_ambiguous_values() -> None:
    assert _as_bool(pd.Series([True, False])).tolist() == [True, False]
    assert _as_bool(pd.Series(["true", "false"])).tolist() == [True, False]
    with pytest.raises(ValueError, match="Invalid boolean"):
        _as_bool(pd.Series(["yes"]))


def test_overlap_is_directional_and_traceable() -> None:
    masks = {
        "a": pd.Series([True, True, False, False]),
        "b": pd.Series([True, False, True, False]),
    }
    table = _overlap_table(masks).set_index(["condition", "outcome"])
    assert table.loc[("a", "b"), "intersection_frame_count"] == 1
    assert table.loc[("a", "b"), "p_outcome_given_condition"] == 0.5
    assert table.loc[("a", "b"), "jaccard"] == pytest.approx(1 / 3)


def test_derivative_rate_uses_t_minus_one_intervals() -> None:
    config = {
        "expected": {"fps": 30.0},
        "analysis": {
            "metrics": [
                {
                    "name": "jump",
                    "frame_flag": "jump_flag",
                    "excluded_leading_frames_from_rate": 1,
                }
            ]
        },
    }
    catalog = pd.DataFrame(
        [
            {
                "motion_name": "m",
                "motion_category": "test",
                "contact_policy": "feet_only",
                "pkl_path": "/tmp/m.pkl",
                "source_bvh": "/tmp/m.bvh",
            }
        ]
    )
    frames = pd.DataFrame(
        {
            "motion_name": ["m"] * 4,
            "jump_flag": [False, True, False, False],
        }
    )
    masks = _metric_masks(config, frames)
    result = _motion_summary(config, catalog, frames, masks).iloc[0]
    assert result["jump_frame_count"] == 1
    assert result["jump_eligible_frame_count"] == 3
    assert result["jump_frame_rate"] == pytest.approx(1 / 3)


def test_verify_manifest_detects_changes(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("stable\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "complete": True,
        "files": [{"path": artifact.name, "size_bytes": artifact.stat().st_size, "sha256": digest}],
    }
    path = tmp_path / "run_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert verify_manifest(path)["ok"] is True
    artifact.write_text("changed\n", encoding="utf-8")
    assert verify_manifest(path)["ok"] is False


def test_formal_visual_review_matches_frozen_catalog(tmp_path: Path) -> None:
    output = tmp_path / "merged.csv"
    result = finalize_visual_review(
        PROJECT / "outputs" / "baseline_failure_analysis_v2" / "tables" / "failure_case_catalog.csv",
        PROJECT / "data" / "visual_review.yaml",
        output,
    )
    merged = pd.read_csv(result)
    assert len(merged) == 12
    assert merged["case_id"].nunique() == 12
    assert set(merged["metric_agreement"]) <= {"agree", "partial", "disagree", "not_applicable"}


def test_formal_manifest_locks_current_analysis_sources() -> None:
    import hashlib

    manifest = json.loads(
        (PROJECT / "outputs" / "baseline_failure_analysis_v2" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["analysis_source_files"]) == 3
    for entry in manifest["analysis_source_files"]:
        path = Path(entry["path"])
        assert path.stat().st_size == entry["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
