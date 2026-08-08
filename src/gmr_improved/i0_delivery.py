"""Create and independently verify the final I0 delivery record."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FROZEN_HASHES = {
    "src/gmr_improved/temporal.py": "c00b37167acc0cf5679a52bbc24c354874a63e5d43560ba986f5109c0ae148a0",
    "src/gmr_improved/temporal_experiment.py": "bdb5aa9b6086daa18741616aa9162aa9e3b84e108b467372f2b4f588598ae746",
    "configs/temporal_gmr_v2.yaml": "4a58ce6a8ea3ad1b4f8e499771bd0a82a4f209e77588e4f9c37aa3e361c17eb5",
    "data/temporal_gmr_heldout_sources.csv": "35e5523c9f798a90745cbb6c92daa2785793f2a630a9775aef87bdd6f4900b03",
}

DELIVERY_ARTIFACTS = [
    "README.md",
    "pyproject.toml",
    "configs/temporal_gmr_v2.yaml",
    "configs/temporal_gmr_heldout_v1.yaml",
    "data/temporal_gmr_heldout_sources.csv",
    "data/temporal_gmr_heldout_core_audit.json",
    "reports/TEMPORAL_GMR_REPORT.md",
    "reports/TEMPORAL_GMR_I0_FINAL_REPORT.md",
    "src/gmr_improved/temporal.py",
    "src/gmr_improved/temporal_experiment.py",
    "src/gmr_improved/heldout_experiment.py",
    "src/gmr_improved/heldout_compare.py",
    "src/gmr_improved/heldout_audit.py",
    "src/gmr_improved/heldout_visualization.py",
    "src/gmr_improved/heldout_visualization_v2.py",
    "src/gmr_improved/heldout_visualization_v3.py",
    "src/gmr_improved/i0_delivery.py",
    "outputs/temporal_gmr_heldout_a0_v1/run_manifest.json",
    "outputs/temporal_gmr_heldout_a1_v1/run_manifest.json",
    "outputs/temporal_gmr_heldout_a0_quality_v1/run_manifest.json",
    "outputs/temporal_gmr_heldout_a1_quality_v1/run_manifest.json",
    "outputs/temporal_gmr_heldout_comparison_v1/comparison_manifest.json",
    "outputs/temporal_gmr_heldout_comparison_v1/comparison_summary.json",
    "outputs/temporal_gmr_heldout_comparison_v1/paired_motion_metrics.csv",
    "outputs/temporal_gmr_heldout_comparison_v1/category_metrics.csv",
    "outputs/temporal_gmr_heldout_visualization_v3/visualization_manifest.json",
    "outputs/temporal_gmr_heldout_visualization_v3/index.html",
    "outputs/temporal_gmr_heldout_visualization_v3/VISUALIZATION_GUIDE.md",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(root: Path, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": relative_path,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_file_records(root: Path, records: Iterable[dict[str, Any]]) -> list[str]:
    mismatches: list[str] = []
    for record in records:
        path = root / record["path"]
        if not path.is_file():
            mismatches.append(f"missing:{record['path']}")
            continue
        if path.stat().st_size != record["size_bytes"]:
            mismatches.append(f"size:{record['path']}")
        if sha256_file(path) != record["sha256"]:
            mismatches.append(f"sha256:{record['path']}")
    return mismatches


def _verify_visualization_manifest(root: Path) -> list[str]:
    directory = root / "outputs/temporal_gmr_heldout_visualization_v3"
    manifest = json.loads((directory / "visualization_manifest.json").read_text(encoding="utf-8"))
    mismatches: list[str] = []
    if not manifest.get("complete") or manifest.get("layout_version") != 3:
        mismatches.append("visualization:completion_or_version")
    for record in manifest.get("outputs", []):
        path = directory / record["path"]
        if not path.is_file():
            mismatches.append(f"visualization:missing:{record['path']}")
        elif path.stat().st_size != record["size_bytes"] or sha256_file(path) != record["sha256"]:
            mismatches.append(f"visualization:hash:{record['path']}")
    for section in ("inputs", "implementation"):
        for record in manifest.get(section, []):
            path = Path(record["path"])
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                mismatches.append(f"visualization:{section}:{record['path']}")
    return mismatches


def validate_i0(root: Path) -> dict[str, Any]:
    mismatches: list[str] = []
    for relative_path, expected in FROZEN_HASHES.items():
        path = root / relative_path
        if not path.is_file() or sha256_file(path) != expected:
            mismatches.append(f"frozen_hash:{relative_path}")

    core_audit = json.loads(
        (root / "data/temporal_gmr_heldout_core_audit.json").read_text(encoding="utf-8")
    )
    if not core_audit.get("ok") or core_audit.get("mismatch_count") != 0:
        mismatches.append("core_audit:not_ok")

    summary = json.loads(
        (root / "outputs/temporal_gmr_heldout_comparison_v1/comparison_summary.json").read_text(encoding="utf-8")
    )
    if summary.get("motion_count") != 15 or summary.get("frame_count") != 91627:
        mismatches.append("comparison:cohort_shape")
    if not summary.get("acceptance", {}).get("heldout_gate_pass"):
        mismatches.append("comparison:gate_not_passed")
    if summary.get("acceptance", {}).get("new_hard_fail_motions"):
        mismatches.append("comparison:new_hard_fail")
    if summary.get("uncalibrated_quality_score_used") is not False:
        mismatches.append("comparison:uncalibrated_score")

    with (root / "data/temporal_gmr_heldout_sources.csv").open(newline="", encoding="utf-8") as stream:
        catalog = list(csv.DictReader(stream))
    if len(catalog) != 15 or sum(int(row["source_frame_count"]) for row in catalog) != 91627:
        mismatches.append("catalog:cohort_shape")

    mismatches.extend(_verify_visualization_manifest(root))
    return {
        "ok": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "motion_count": summary.get("motion_count"),
        "frame_count": summary.get("frame_count"),
        "heldout_gate_pass": summary.get("acceptance", {}).get("heldout_gate_pass"),
        "uncalibrated_quality_score_used": summary.get("uncalibrated_quality_score_used"),
        "visualization_layout_version": 3,
    }


def create_delivery(root: Path, manifest_path: Path, audit_path: Path) -> tuple[Path, Path]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    audit_path = audit_path.resolve()
    for output in (manifest_path, audit_path):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite final record: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)

    validation = validate_i0(root)
    if not validation["ok"]:
        raise ValueError(f"I0 validation failed: {validation['mismatches']}")
    records = [file_record(root, relative_path) for relative_path in DELIVERY_ARTIFACTS]
    manifest = {
        "schema_version": 1,
        "stage": "I0_Temporal_GMR",
        "status": "completed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
        "artifact_count": len(records),
        "artifacts": records,
        "notes": [
            "PLAN.md is intentionally excluded because it records this manifest hash after creation.",
            "The final audit file is intentionally excluded to avoid self-reference.",
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
        "nested_i0_validation": validation,
    }
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path, audit_path
