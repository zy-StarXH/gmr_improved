"""Create and independently verify the final Collision-GMR I1 delivery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .i0_delivery import file_record, sha256_file, verify_file_records


FROZEN_HASHES = {
    "src/gmr_improved/temporal.py": "c00b37167acc0cf5679a52bbc24c354874a63e5d43560ba986f5109c0ae148a0",
    "src/gmr_improved/collision.py": "04b08b58fb0782066645fbcf3574cb5155e8e17662b9f4129fda9a2d7fefeb40",
    "src/gmr_improved/collision_model.py": "9c6415e5fe1ff9696cb180e694e303b4a96eefc98971c2fa229a6843508b975e",
    "src/gmr_improved/collision_experiment.py": "8500e264b8ec662c6e8187bc08407dbe3859c78b97cc66a516b56f9395e288b9",
    "src/gmr_improved/collision_cli.py": "1dda38c82fa50fb564122a7bd4bc8a4a9bac38c1f552d763f5c1f253779dcd17",
    "src/gmr_improved/collision_compare.py": "88a1c40439994d81e5b49e2f69bffa64d705b0ea71c6239d0e2b709c4a79b90d",
    "src/gmr_improved/collision_event_audit.py": "134dfd47f180bc4cd006154fecea6e88984a15a3cf10c23c02f1320d78886ea8",
    "src/gmr_improved/collision_geometry_audit.py": "b80ee2e9e470b77225441fe48bc7b3edcb3064ecebc37325ac5cae51397c6a79",
    "configs/collision_gmr_v1.yaml": "520f82b80fbd96c1bbcdc8e2881db5e9bd435e35c19b1e95cac1f7be2ec3444a",
    "configs/collision_gmr_heldout_v1.yaml": "0a5aa5b535271abec40cbeb8afea1405651a8979cce58e098b75db624694013b",
    "assets/collision_g1_v1/g1_mocap_29dof_collision_named.xml": "02e330272c37cdec968cd468851aaa7b741501e80a943293081cfbc897eec7ff",
    "assets/collision_g1_v1/collision_pairs.csv": "bbac0b68e7e69fe218e310eecc6a0dafa61aba3ae7bbdf15c5ce6fe569d971ff",
    "assets/collision_g1_v1/collision_model_audit.json": "ac48303565d8e373dcbc31a1fc9001ed8f4f749e3e624db22bf049b77c87df27",
}

DELIVERY_ARTIFACTS = [
    "README.md",
    "pyproject.toml",
    "configs/collision_gmr_v1.yaml",
    "configs/collision_gmr_heldout_v1.yaml",
    "assets/collision_g1_v1/g1_mocap_29dof_collision_named.xml",
    "assets/collision_g1_v1/collision_pairs.csv",
    "assets/collision_g1_v1/geom_name_map.csv",
    "assets/collision_g1_v1/collision_model_audit.json",
    "assets/collision_g1_v1/collision_model_manifest.json",
    "reports/COLLISION_GMR_I1_FINAL_REPORT.md",
    "src/gmr_improved/collision.py",
    "src/gmr_improved/collision_model.py",
    "src/gmr_improved/collision_experiment.py",
    "src/gmr_improved/collision_compare.py",
    "src/gmr_improved/collision_event_audit.py",
    "src/gmr_improved/collision_geometry_audit.py",
    "src/gmr_improved/viewer_compat.py",
    "src/gmr_improved/i1_delivery.py",
    "outputs/collision_gmr_development_v1/run_manifest.json",
    "outputs/collision_gmr_development_v1_quality/run_manifest.json",
    "outputs/collision_gmr_development_v1_comparison_v2/comparison_manifest.json",
    "outputs/collision_gmr_development_v1_comparison_v2/comparison_summary.json",
    "outputs/collision_gmr_development_v1_event_audit/audit_manifest.json",
    "outputs/collision_gmr_development_v1_event_audit/event_coverage_audit.json",
    "outputs/collision_gmr_development_v1_geometry_audit/audit_manifest.json",
    "outputs/collision_gmr_development_v1_geometry_audit/geometry_audit_summary.json",
    "outputs/collision_gmr_heldout_a2_v1/run_manifest.json",
    "outputs/collision_gmr_heldout_a2_v1_quality/run_manifest.json",
    "outputs/collision_gmr_heldout_a2_v1_comparison/comparison_manifest.json",
    "outputs/collision_gmr_heldout_a2_v1_comparison/comparison_summary.json",
    "outputs/collision_gmr_heldout_a2_v1_comparison/paired_motion_metrics.csv",
    "outputs/collision_gmr_heldout_a2_v1_comparison/category_metrics.csv",
    "outputs/collision_gmr_heldout_a2_v1_event_audit/audit_manifest.json",
    "outputs/collision_gmr_heldout_a2_v1_event_audit/event_coverage_audit.json",
    "outputs/collision_gmr_heldout_a2_v1_geometry_audit/audit_manifest.json",
    "outputs/collision_gmr_heldout_a2_v1_geometry_audit/geometry_audit_summary.json",
    "outputs/visualization_compat/dance1_subject2_a2_collision_v1.pkl",
]


def validate_i1(root: Path) -> dict[str, Any]:
    mismatches: list[str] = []
    for relative_path, expected in FROZEN_HASHES.items():
        path = root / relative_path
        if not path.is_file() or sha256_file(path) != expected:
            mismatches.append(f"frozen_hash:{relative_path}")

    model_audit = json.loads(
        (root / "assets/collision_g1_v1/collision_model_audit.json").read_text(
            encoding="utf-8"
        )
    )
    equivalence = model_audit.get("model_equivalence", {})
    pairs = model_audit.get("pair_audit", {})
    if not equivalence.get("ok") or equivalence.get("mismatch_count") != 0:
        mismatches.append("model_equivalence:not_ok")
    if pairs.get("included_geom_pair_count") != 362 or pairs.get(
        "included_body_pair_count"
    ) != 193:
        mismatches.append("pair_audit:count")
    if pairs.get("below_minimum_at_neutral_count") != 0:
        mismatches.append("pair_audit:neutral_below_minimum")

    comparisons: dict[str, Any] = {}
    for cohort, expected_frames in (("development", 90540), ("heldout", 91627)):
        if cohort == "development":
            path = root / "outputs/collision_gmr_development_v1_comparison_v2/comparison_summary.json"
        else:
            path = root / "outputs/collision_gmr_heldout_a2_v1_comparison/comparison_summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        comparisons[cohort] = summary
        if summary.get("motion_count") != 15 or summary.get("frame_count") != expected_frames:
            mismatches.append(f"comparison:{cohort}:cohort_shape")
        if not summary.get("acceptance", {}).get("development_gate_pass"):
            mismatches.append(f"comparison:{cohort}:gate")
        if summary.get("acceptance", {}).get("new_hard_fail_motions"):
            mismatches.append(f"comparison:{cohort}:new_hard_fail")
        if summary.get("uncalibrated_quality_score_used") is not False:
            mismatches.append(f"comparison:{cohort}:uncalibrated_score")

    event_audit = json.loads(
        (root / "outputs/collision_gmr_heldout_a2_v1_event_audit/event_coverage_audit.json").read_text(
            encoding="utf-8"
        )
    )
    heldout = comparisons["heldout"]
    if event_audit.get("audited_body_pair_count") != 193:
        mismatches.append("event_audit:pair_count")
    if event_audit.get("a1", {}).get("event_count", {}).get("total") != heldout[
        "cohort_metrics"
    ]["self_collision_nonhand_event_count"]["a1"]:
        mismatches.append("event_audit:a1_total")
    if event_audit.get("a2", {}).get("event_count", {}).get("total") != heldout[
        "cohort_metrics"
    ]["self_collision_nonhand_event_count"]["a2"]:
        mismatches.append("event_audit:a2_total")
    if event_audit.get("delta", {}).get("event_count", {}).get("audited", 0) >= 0:
        mismatches.append("event_audit:audited_not_improved")

    geometry = json.loads(
        (root / "outputs/collision_gmr_heldout_a2_v1_geometry_audit/geometry_audit_summary.json").read_text(
            encoding="utf-8"
        )
    )
    if geometry.get("motion_count") != 15 or geometry.get("frame_count") != 91627:
        mismatches.append("geometry:cohort_shape")
    if geometry.get("audited_geom_pair_count") != 362:
        mismatches.append("geometry:pair_count")
    for metric in ("below_minimum_frame_count", "penetrating_frame_count"):
        values = geometry.get("totals", {}).get(metric, {})
        if values.get("delta", 0) >= 0:
            mismatches.append(f"geometry:{metric}:not_improved")
    if geometry.get("totals", {}).get("penetrating_frame_count", {}).get("a2", 0) <= 0:
        mismatches.append("geometry:negative_result_missing")

    for cohort, path in (
        ("development", root / "outputs/collision_gmr_development_v1/run_manifest.json"),
        ("heldout", root / "outputs/collision_gmr_heldout_a2_v1/run_manifest.json"),
    ):
        run = json.loads(path.read_text(encoding="utf-8"))
        if not run.get("complete") or run.get("cohort", {}).get("motion_count") != 15:
            mismatches.append(f"generation:{cohort}:incomplete")

    return {
        "ok": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "development_gate_pass": comparisons.get("development", {})
        .get("acceptance", {})
        .get("development_gate_pass"),
        "heldout_gate_pass": comparisons.get("heldout", {})
        .get("acceptance", {})
        .get("development_gate_pass"),
        "heldout_motion_count": comparisons.get("heldout", {}).get("motion_count"),
        "heldout_frame_count": comparisons.get("heldout", {}).get("frame_count"),
        "remaining_penetrating_frames": geometry.get("totals", {})
        .get("penetrating_frame_count", {})
        .get("a2"),
        "uncalibrated_quality_score_used": comparisons.get("heldout", {}).get(
            "uncalibrated_quality_score_used"
        ),
    }


def create_delivery(root: Path, manifest_path: Path, audit_path: Path) -> tuple[Path, Path]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    audit_path = audit_path.resolve()
    for output in (manifest_path, audit_path):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite final record: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)

    validation = validate_i1(root)
    if not validation["ok"]:
        raise ValueError(f"I1 validation failed: {validation['mismatches']}")
    records = [file_record(root, relative_path) for relative_path in DELIVERY_ARTIFACTS]
    manifest = {
        "schema_version": 1,
        "stage": "I1_Collision_GMR",
        "status": "completed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
        "artifact_count": len(records),
        "artifacts": records,
        "notes": [
            "PLAN.md is excluded because it records this manifest hash after creation.",
            "The final audit file is excluded to avoid self-reference.",
            "Passing the gate does not imply strict collision-free output; the remaining penetration count is explicitly validated.",
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    delivery_mismatches = verify_file_records(root, loaded["artifacts"])
    audit = {
        "schema_version": 1,
        "ok": not delivery_mismatches,
        "mismatch_count": len(delivery_mismatches),
        "mismatches": delivery_mismatches,
        "delivery_manifest": {
            "path": str(manifest_path),
            "size_bytes": manifest_path.stat().st_size,
            "sha256": sha256_file(manifest_path),
        },
        "artifact_count_verified": len(loaded["artifacts"]),
        "nested_i1_validation": validation,
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, audit_path
