from __future__ import annotations

import json
from pathlib import Path

import mujoco

from gmr_improved.collision_model import (
    CollisionAuditParameters,
    audit_collision_pairs,
    prepare_collision_model,
)


GMR_XML = Path("/root/gpufree-data/GMR/assets/unitree_g1/g1_mocap_29dof.xml")


def test_collision_model_is_equivalent_and_pairs_are_audited(tmp_path: Path) -> None:
    output = tmp_path / "collision_model"
    manifest_path = prepare_collision_model(GMR_XML, output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads((output / "collision_model_audit.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    assert audit["model_equivalence"]["ok"] is True
    assert audit["model_equivalence"]["mismatch_count"] == 0
    assert audit["assigned_geom_name_count"] == 71
    assert audit["pair_audit"]["included_geom_pair_count"] == 362
    assert audit["pair_audit"]["included_body_pair_count"] == 193
    assert audit["pair_audit"]["below_minimum_at_neutral_count"] == 0
    model = mujoco.MjModel.from_xml_path(
        str(output / "g1_mocap_29dof_collision_named.xml")
    )
    names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index)
        for index in range(model.ngeom)
    ]
    assert all(names)
    assert len(names) == len(set(names))


def test_pair_audit_rejects_relaxed_bound_and_keeps_hand_excluded(tmp_path: Path) -> None:
    output = tmp_path / "collision_model"
    prepare_collision_model(GMR_XML, output)
    derived = output / "g1_mocap_29dof_collision_named.xml"
    audit, records, _ = audit_collision_pairs(derived, CollisionAuditParameters())
    assert audit["mink_expanded_pair_count"] == len(records)
    assert all(row["tree_distance"] >= 3 for row in records)
    assert all(
        "wrist" not in row[side]
        for row in records
        for side in ("body_a_name", "body_b_name")
    )
