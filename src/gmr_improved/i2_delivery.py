"""Create and independently verify the final Contact-GMR I2 delivery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .i0_delivery import file_record, sha256_file, verify_file_records


FROZEN_HASHES = {
    "src/gmr_improved/temporal.py": "c00b37167acc0cf5679a52bbc24c354874a63e5d43560ba986f5109c0ae148a0",
    "src/gmr_improved/collision.py": "04b08b58fb0782066645fbcf3574cb5155e8e17662b9f4129fda9a2d7fefeb40",
    "src/gmr_improved/contact.py": "8c57d5e13def9661840a1281cea2202324dc486fc7481e4a62046adec6e32e15",
    "src/gmr_improved/contact_input_audit.py": "6b442b30fb37b7d5e21f5e14d2fb7997c8049e53cacee1a6f6be7cdb2c52e0f6",
    "src/gmr_improved/contact_experiment.py": "2b65a0d88e6f456e4cb180b9b2a22ef75d64b035a1f635c7eef744a3f7899ed5",
    "src/gmr_improved/contact_cli.py": "8ed9077c59efff73607a1ee27336e2ada9ab315cac860f4c26407eb25532fd54",
    "src/gmr_improved/contact_compare.py": "f0ebc6340e35cd41b0e4c385db7dfa88335d1b649dd1d25d40a9cdd360c2d92a",
    "src/gmr_improved/contact_audit.py": "3a28505e63e776d3604fccae81ff9ee97044a0421af5c38f00bc993d50ef04a2",
    "configs/contact_gmr_v1.yaml": "679d6d35039d67826dfea05e87cc96b8692789d29103e751862cc94403330779",
    "configs/contact_gmr_v2.yaml": "b16d9b042682b092691366b32ff36047c04cfd50e76225e22199a965b397cb56",
    "configs/contact_gmr_heldout_v2.yaml": "5faeb5ab565d82b647a1491e2db1924e96df57c6d91d0404033f11ac61f837b9",
    "assets/contact_gmr_v1/contact_input_audit.json": "9cfc9b1cadb40732a0e8ab2a24d2d45a60f7be631e2f4f85bbbb0b5e59a7c779",
    "assets/contact_gmr_v2/contact_input_audit.json": "af13a4462343f2507c942b9b9d2bfa1ccc0a25e1fc903999878b3befd57d89d8",
    "assets/contact_gmr_heldout_v2/contact_input_audit.json": "6ac0c9334b771c227832652131f41f74a530060780119fd66d9cf1ff8cecf9e7",
}


DELIVERY_ARTIFACTS = [
    "README.md",
    "pyproject.toml",
    "configs/contact_gmr_v1.yaml",
    "configs/contact_gmr_v2.yaml",
    "configs/contact_gmr_heldout_v2.yaml",
    "assets/contact_gmr_v1/contact_input_audit.json",
    "assets/contact_gmr_v1/source_contact_metrics.csv",
    "assets/contact_gmr_v2/contact_input_audit.json",
    "assets/contact_gmr_v2/source_contact_metrics.csv",
    "assets/contact_gmr_heldout_v2/contact_input_audit.json",
    "assets/contact_gmr_heldout_v2/source_contact_metrics.csv",
    "reports/CONTACT_GMR_V1_DEVELOPMENT_REPORT.md",
    "reports/CONTACT_GMR_I2_FINAL_REPORT.md",
    "src/gmr_improved/contact.py",
    "src/gmr_improved/contact_input_audit.py",
    "src/gmr_improved/contact_experiment.py",
    "src/gmr_improved/contact_cli.py",
    "src/gmr_improved/contact_compare.py",
    "src/gmr_improved/contact_compare_cli.py",
    "src/gmr_improved/contact_audit.py",
    "src/gmr_improved/contact_audit_cli.py",
    "src/gmr_improved/viewer_compat.py",
    "src/gmr_improved/i2_delivery.py",
    "outputs/contact_gmr_development_v1/run_manifest.json",
    "outputs/contact_gmr_development_v1_quality/run_manifest.json",
    "outputs/contact_gmr_development_v1_comparison/comparison_manifest.json",
    "outputs/contact_gmr_development_v1_comparison/comparison_summary.json",
    "data/contact_gmr_development_v1_audit.json",
    "outputs/contact_gmr_development_v2/run_manifest.json",
    "outputs/contact_gmr_development_v2_quality/run_manifest.json",
    "outputs/contact_gmr_development_v2_comparison/comparison_manifest.json",
    "outputs/contact_gmr_development_v2_comparison/comparison_summary.json",
    "outputs/contact_gmr_development_v2_comparison/paired_motion_metrics.csv",
    "outputs/contact_gmr_development_v2_comparison/policy_metrics.csv",
    "data/contact_gmr_development_v2_audit.json",
    "outputs/contact_gmr_heldout_v2/run_manifest.json",
    "outputs/contact_gmr_heldout_v2_quality/run_manifest.json",
    "outputs/contact_gmr_heldout_v2_comparison/comparison_manifest.json",
    "outputs/contact_gmr_heldout_v2_comparison/comparison_summary.json",
    "outputs/contact_gmr_heldout_v2_comparison/paired_motion_metrics.csv",
    "outputs/contact_gmr_heldout_v2_comparison/policy_metrics.csv",
    "data/contact_gmr_heldout_v2_audit.json",
    "outputs/visualization_compat/walk3_subject3_a2_collision_v1.pkl",
    "outputs/visualization_compat/walk3_subject3_a3_contact_v2.pkl",
    "outputs/visualization_compat/dance1_subject2_a2_collision_for_contact.pkl",
    "outputs/visualization_compat/dance1_subject2_a3_contact_v2.pkl",
]


def _load(root: Path, relative_path: str) -> dict[str, Any]:
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


def validate_i2(root: Path) -> dict[str, Any]:
    mismatches: list[str] = []
    for relative_path, expected in FROZEN_HASHES.items():
        path = root / relative_path
        if not path.is_file() or sha256_file(path) != expected:
            mismatches.append(f"frozen_hash:{relative_path}")

    comparisons = {
        "v1_development": _load(
            root,
            "outputs/contact_gmr_development_v1_comparison/comparison_summary.json",
        ),
        "v2_development": _load(
            root,
            "outputs/contact_gmr_development_v2_comparison/comparison_summary.json",
        ),
        "v2_heldout": _load(
            root,
            "outputs/contact_gmr_heldout_v2_comparison/comparison_summary.json",
        ),
    }
    expected_frames = {
        "v1_development": 90540,
        "v2_development": 90540,
        "v2_heldout": 91627,
    }
    for name, summary in comparisons.items():
        if summary.get("motion_count") != 15 or summary.get("frame_count") != expected_frames[name]:
            mismatches.append(f"comparison:{name}:cohort_shape")
        if summary.get("uncalibrated_quality_score_used") is not False:
            mismatches.append(f"comparison:{name}:uncalibrated_score")
        if summary.get("acceptance", {}).get("new_hard_fail_motions"):
            mismatches.append(f"comparison:{name}:new_hard_fail")
        if not summary.get("acceptance", {}).get("floor_motion_exact_noop"):
            mismatches.append(f"comparison:{name}:floor_noop")
    if comparisons["v1_development"]["acceptance"].get("contact_gate_pass") is not False:
        mismatches.append("comparison:v1_development:negative_result_missing")
    if comparisons["v1_development"]["acceptance"].get("fidelity_gate_pass") is not False:
        mismatches.append("comparison:v1_development:fidelity_failure_missing")
    for name in ("v2_development", "v2_heldout"):
        if comparisons[name]["acceptance"].get("contact_gate_pass") is not True:
            mismatches.append(f"comparison:{name}:gate")

    audits = {
        "v1_development": _load(root, "data/contact_gmr_development_v1_audit.json"),
        "v2_development": _load(root, "data/contact_gmr_development_v2_audit.json"),
        "v2_heldout": _load(root, "data/contact_gmr_heldout_v2_audit.json"),
    }
    for name, audit in audits.items():
        if not audit.get("ok"):
            mismatches.append(f"audit:{name}:not_ok")
        if audit.get("base_integrity_audit", {}).get("mismatch_count") != 0:
            mismatches.append(f"audit:{name}:integrity_mismatch")
        if audit.get("contact_invariants", {}).get("failure_count") != 0:
            mismatches.append(f"audit:{name}:contact_invariant")

    heldout = comparisons["v2_heldout"]
    feet = heldout["cohort_metrics"]["feet_only"]
    for metric in (
        "foot_slide_frame_rate",
        "ground_penetration_frame_rate",
        "severe_ground_penetration_frame_rate",
        "undesired_ground_contact_frame_rate",
    ):
        if feet[metric]["delta"] >= 0.0:
            mismatches.append(f"heldout:{metric}:not_improved")
    overall = heldout["cohort_metrics"]["overall"]
    if overall["root_jerk_p95_m_s3"]["delta"] <= 0.0:
        mismatches.append("heldout:root_jerk_negative_result_missing")
    if overall["self_collision_nonhand_event_count"]["delta"] <= 0.0:
        mismatches.append("heldout:collision_event_negative_result_missing")
    heldout_contact_stats = audits["v2_heldout"]["contact_invariants"][
        "policy_statistics"
    ]["feet_only"]
    if heldout_contact_stats["max_post_ground_penetration_m"] <= 0.005:
        mismatches.append("heldout:residual_penetration_negative_result_missing")

    for name, path in (
        ("v1_development", "outputs/contact_gmr_development_v1/run_manifest.json"),
        ("v2_development", "outputs/contact_gmr_development_v2/run_manifest.json"),
        ("v2_heldout", "outputs/contact_gmr_heldout_v2/run_manifest.json"),
    ):
        run = _load(root, path)
        if not run.get("complete") or not run.get("formal_run"):
            mismatches.append(f"generation:{name}:incomplete")

    return {
        "ok": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "v1_development_gate_pass": comparisons["v1_development"]["acceptance"][
            "contact_gate_pass"
        ],
        "v2_development_gate_pass": comparisons["v2_development"]["acceptance"][
            "contact_gate_pass"
        ],
        "v2_heldout_gate_pass": heldout["acceptance"]["contact_gate_pass"],
        "heldout_motion_count": heldout["motion_count"],
        "heldout_frame_count": heldout["frame_count"],
        "heldout_residual_max_penetration_m": heldout_contact_stats[
            "max_post_ground_penetration_m"
        ],
        "heldout_root_jerk_p95_delta_m_s3": overall["root_jerk_p95_m_s3"]["delta"],
        "uncalibrated_quality_score_used": heldout["uncalibrated_quality_score_used"],
    }


def create_delivery(root: Path, manifest_path: Path, audit_path: Path) -> tuple[Path, Path]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    audit_path = audit_path.resolve()
    for output in (manifest_path, audit_path):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite final record: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
    validation = validate_i2(root)
    if not validation["ok"]:
        raise ValueError(f"I2 validation failed: {validation['mismatches']}")
    records = [file_record(root, relative_path) for relative_path in DELIVERY_ARTIFACTS]
    manifest = {
        "schema_version": 1,
        "stage": "I2_Contact_GMR",
        "status": "completed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
        "artifact_count": len(records),
        "artifacts": records,
        "notes": [
            "PLAN.md is excluded because it records this manifest hash after creation.",
            "The final audit file is excluded to avoid self-reference.",
            "The failed v1 development result and the held-out residual penetration/root-jerk negative results are mandatory delivery evidence.",
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
        "nested_i2_validation": validation,
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, audit_path
