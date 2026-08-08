"""Hash-gated A3 Contact-GMR runner for development and held-out cohorts."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import pickle
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import yaml

from .collision import CollisionGMRConfig
from .collision_experiment import _verify_collision_audit
from .contact import (
    ContactGMRConfig,
    ContactGeneralMotionRetargeting,
    infer_human_contact_sequence,
)
from .temporal import TemporalGMRConfig
from .temporal_experiment import (
    CATALOG_COLUMNS,
    TemporalRunResult,
    _git_state,
    _joint_names,
    _prepare_empty_output,
    _read_catalog,
    _require_hash,
    _source_fps,
    _write_json,
    _write_pickle_atomic,
    sha256_file,
)


def load_contact_experiment_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Contact experiment config must be a schema_version=1 mapping")
    temporal = dict(raw.get("temporal_gmr", {}))
    collision = dict(raw.get("collision_gmr", {}))
    if "hand_patterns" in collision:
        collision["hand_patterns"] = tuple(collision["hand_patterns"])
    raw["_config_path"] = str(config_path)
    raw["_temporal_config"] = TemporalGMRConfig(**temporal)
    raw["_collision_config"] = CollisionGMRConfig(**collision)
    raw["_contact_config"] = ContactGMRConfig(**dict(raw.get("contact_gmr", {})))
    if raw.get("formal_role") not in {"development", "heldout"}:
        raise ValueError("formal_role must be development or heldout")
    if not isinstance(raw.get("experiment_name"), str) or not raw["experiment_name"]:
        raise ValueError("experiment_name must be a non-empty string")
    return raw


def _verify_contact_input_audit(
    path: Path,
    config: ContactGMRConfig,
    catalog_path: Path,
) -> dict[str, Any]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    if not audit.get("ok"):
        raise ValueError("Source-human contact input audit is not passing")
    if audit.get("parameters") != config.as_dict():
        raise ValueError("Contact input audit parameters differ from runtime config")
    catalog = audit.get("inputs", {}).get("catalog", {})
    if catalog.get("path") != str(catalog_path) or catalog.get("sha256") != sha256_file(
        catalog_path
    ):
        raise ValueError("Contact input audit belongs to a different source catalog")
    policy = audit.get("policy_audit", {})
    if policy.get("feet_only_any_contact_frame_count", 0) <= 0:
        raise ValueError("Contact input audit inferred no feet_only contacts")
    if not policy.get("floor_motion_semantic_noop"):
        raise ValueError("Contact input audit did not preserve floor_motion no-op")
    return audit


def _load_reference_payloads(catalog_path: Path) -> dict[str, dict[str, Any]]:
    rows = _read_catalog(catalog_path)
    payloads: dict[str, dict[str, Any]] = {}
    for row in rows:
        path = Path(row["pkl_path"]).expanduser().resolve()
        _require_hash(path, row["pkl_sha256"], f"A2 reference PKL {row['motion_name']}")
        with path.open("rb") as stream:
            payload = pickle.load(stream)
        payloads[row["motion_name"]] = payload
    return payloads


def run_contact_retargeting(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    motions: Sequence[str] | None = None,
    max_frames: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> TemporalRunResult:
    config = load_contact_experiment_config(config_path)
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty_output(destination)
    retargeted_dir = destination / "retargeted"
    diagnostics_dir = destination / "diagnostics"
    retargeted_dir.mkdir()
    diagnostics_dir.mkdir()

    paths = config["paths"]
    frozen = config["frozen_inputs"]
    named_paths = {
        "source catalog": Path(paths["source_catalog"]).expanduser().resolve(),
        "A2 reference catalog": Path(paths["a2_reference_catalog"]).expanduser().resolve(),
        "GMR implementation": Path(paths["gmr_motion_retarget"]).expanduser().resolve(),
        "LAFAN1 loader": Path(paths["gmr_lafan1_loader"]).expanduser().resolve(),
        "IK config": Path(paths["gmr_ik_config"]).expanduser().resolve(),
        "original robot XML": Path(paths["original_robot_xml"]).expanduser().resolve(),
        "quality config": Path(paths["quality_config"]).expanduser().resolve(),
        "derived robot XML": Path(paths["derived_robot_xml"]).expanduser().resolve(),
        "collision pair CSV": Path(paths["collision_pairs_csv"]).expanduser().resolve(),
        "collision model audit": Path(paths["collision_model_audit"]).expanduser().resolve(),
        "contact input audit": Path(paths["contact_input_audit"]).expanduser().resolve(),
        "Temporal-GMR implementation": Path(paths["temporal_implementation"]).expanduser().resolve(),
        "Temporal-GMR experiment implementation": Path(paths["temporal_experiment_implementation"]).expanduser().resolve(),
        "Temporal-GMR v2 config": Path(paths["temporal_v2_config"]).expanduser().resolve(),
        "collision implementation": Path(paths["collision_implementation"]).expanduser().resolve(),
        "collision model implementation": Path(paths["collision_model_implementation"]).expanduser().resolve(),
        "collision experiment implementation": Path(paths["collision_experiment_implementation"]).expanduser().resolve(),
        "collision CLI implementation": Path(paths["collision_cli_implementation"]).expanduser().resolve(),
        "contact implementation": Path(paths["contact_implementation"]).expanduser().resolve(),
        "contact input audit implementation": Path(paths["contact_input_audit_implementation"]).expanduser().resolve(),
        "contact experiment implementation": Path(paths["contact_experiment_implementation"]).expanduser().resolve(),
        "contact CLI implementation": Path(paths["contact_cli_implementation"]).expanduser().resolve(),
    }
    hash_keys = {
        "source catalog": "source_catalog_sha256",
        "A2 reference catalog": "a2_reference_catalog_sha256",
        "GMR implementation": "gmr_motion_retarget_sha256",
        "LAFAN1 loader": "gmr_lafan1_loader_sha256",
        "IK config": "gmr_ik_config_sha256",
        "original robot XML": "original_robot_xml_sha256",
        "quality config": "quality_config_sha256",
        "derived robot XML": "derived_robot_xml_sha256",
        "collision pair CSV": "collision_pairs_csv_sha256",
        "collision model audit": "collision_model_audit_sha256",
        "contact input audit": "contact_input_audit_sha256",
        "Temporal-GMR implementation": "temporal_implementation_sha256",
        "Temporal-GMR experiment implementation": "temporal_experiment_implementation_sha256",
        "Temporal-GMR v2 config": "temporal_v2_config_sha256",
        "collision implementation": "collision_implementation_sha256",
        "collision model implementation": "collision_model_implementation_sha256",
        "collision experiment implementation": "collision_experiment_implementation_sha256",
        "collision CLI implementation": "collision_cli_implementation_sha256",
        "contact implementation": "contact_implementation_sha256",
        "contact input audit implementation": "contact_input_audit_implementation_sha256",
        "contact experiment implementation": "contact_experiment_implementation_sha256",
        "contact CLI implementation": "contact_cli_implementation_sha256",
    }
    for label, path in named_paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        _require_hash(path, frozen[hash_keys[label]], label)

    temporal_config: TemporalGMRConfig = config["_temporal_config"]
    collision_config: CollisionGMRConfig = config["_collision_config"]
    contact_config: ContactGMRConfig = config["_contact_config"]
    _verify_collision_audit(named_paths["collision model audit"], collision_config)
    _verify_contact_input_audit(
        named_paths["contact input audit"],
        contact_config,
        named_paths["source catalog"],
    )
    gmr_root = Path(paths["gmr_root"]).expanduser().resolve()
    git_state = _git_state(gmr_root)
    if git_state["commit"] != frozen["gmr_commit"]:
        raise ValueError("GMR commit differs from the frozen Contact-GMR input")

    rows = _read_catalog(named_paths["source catalog"])
    reference_rows = _read_catalog(named_paths["A2 reference catalog"])
    if {row["motion_name"] for row in rows} != {
        row["motion_name"] for row in reference_rows
    }:
        raise ValueError("Source and A2-reference catalogs contain different motions")
    references = _load_reference_payloads(named_paths["A2 reference catalog"])
    selected = set(motions or ())
    if selected:
        missing = selected - {row["motion_name"] for row in rows}
        if missing:
            raise ValueError(f"Requested motions absent from frozen catalog: {sorted(missing)}")
        rows = [row for row in rows if row["motion_name"] in selected]
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be >= 1")
    formal = not selected and max_frames is None
    if formal and len(rows) != int(frozen["motion_count"]):
        raise ValueError("Formal Contact-GMR run has the wrong motion count")

    from general_motion_retargeting.utils.lafan1 import load_bvh_file

    catalog_rows: list[dict[str, str]] = []
    manifest_inputs: list[dict[str, Any]] = []
    total_frames = 0
    run_started = time.perf_counter()
    for sequence_index, row in enumerate(rows, start=1):
        name = row["motion_name"]
        source_bvh = Path(row["source_bvh"]).expanduser().resolve()
        _require_hash(source_bvh, row["source_bvh_sha256"], f"source BVH {name}")
        if progress:
            progress(f"[{sequence_index}/{len(rows)}] Contact-GMR {name}")
        all_frames, human_height = load_bvh_file(str(source_bvh), format="lafan1")
        source_fps = _source_fps(source_bvh)
        contact_sequence = infer_human_contact_sequence(
            all_frames,
            source_fps,
            row["contact_policy"],
            contact_config,
        )
        source_frame_count = len(all_frames)
        frames = all_frames if max_frames is None else all_frames[:max_frames]
        contacts = contact_sequence.frames[: len(frames)]
        if not frames:
            raise ValueError(f"No frames selected for {name}")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            retargeter = ContactGeneralMotionRetargeting(
                src_human="bvh_lafan1",
                tgt_robot="unitree_g1",
                actual_human_height=float(human_height),
                solver=str(config["gmr"]["solver"]),
                damping=float(config["gmr"]["damping"]),
                verbose=False,
                temporal_config=temporal_config,
                collision_config=collision_config,
                derived_robot_xml=named_paths["derived robot XML"],
                collision_pairs_csv=named_paths["collision pair CSV"],
                contact_config=contact_config,
                contact_policy=row["contact_policy"],
            )
        sequence_started = time.perf_counter()
        qpos = np.empty((len(frames), retargeter.model.nq), dtype=np.float64)
        for frame_index, (human_frame, contact_frame) in enumerate(
            zip(frames, contacts, strict=True)
        ):
            qpos[frame_index] = retargeter.retarget(human_frame, contact_frame)
        elapsed = time.perf_counter() - sequence_started
        if qpos.shape != (len(frames), 36) or not np.isfinite(qpos).all():
            raise RuntimeError(f"Invalid Contact-GMR qpos for {name}: {qpos.shape}")

        output_path = retargeted_dir / f"{name}.pkl"
        payload = {
            "fps": temporal_config.output_fps,
            "root_pos": qpos[:, :3],
            "root_rot": qpos[:, 3:7][:, [1, 2, 3, 0]],
            "dof_pos": qpos[:, 7:],
            "dof_names": _joint_names(retargeter.model),
        }
        _write_pickle_atomic(payload, output_path)
        with output_path.open("rb") as stream:
            roundtrip = pickle.load(stream)
        for field in ("root_pos", "root_rot", "dof_pos"):
            np.testing.assert_array_equal(roundtrip[field], payload[field])

        diagnostic_lengths = (
            len(retargeter.frame_diagnostics),
            len(retargeter.collision_frame_diagnostics),
            len(retargeter.contact_frame_diagnostics),
            len(contacts),
        )
        if len(set(diagnostic_lengths)) != 1:
            raise RuntimeError(f"Diagnostic frame mismatch for {name}: {diagnostic_lengths}")
        diagnostic_rows: list[dict[str, Any]] = []
        for temporal_item, collision_item, contact_item, source_item in zip(
            retargeter.frame_diagnostics,
            retargeter.collision_frame_diagnostics,
            retargeter.contact_frame_diagnostics,
            contacts,
            strict=True,
        ):
            indices = {
                temporal_item.frame_index,
                collision_item.frame_index,
                contact_item.frame_index,
                source_item.frame_index,
            }
            if len(indices) != 1:
                raise RuntimeError("Temporal/collision/contact diagnostics lost alignment")
            diagnostic_row = asdict(temporal_item)
            collision_row = asdict(collision_item)
            collision_row.pop("frame_index")
            contact_row = asdict(contact_item)
            contact_row.pop("frame_index")
            source_row = asdict(source_item)
            source_row.pop("frame_index")
            diagnostic_row.update({f"collision_{key}": value for key, value in collision_row.items()})
            diagnostic_row.update({f"contact_{key}": value for key, value in contact_row.items()})
            diagnostic_row.update({f"source_{key}": value for key, value in source_row.items()})
            diagnostic_rows.append(diagnostic_row)
        diagnostic_path = diagnostics_dir / f"{name}.csv"
        with diagnostic_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(diagnostic_rows[0]))
            writer.writeheader()
            writer.writerows(diagnostic_rows)

        constrained = [item for item in retargeter.frame_diagnostics if item.trust_region_enabled]
        max_ratio = max((item.max_trust_region_ratio or 0.0 for item in constrained), default=0.0)
        max_velocity = max((item.max_joint_velocity_rad_s or 0.0 for item in constrained), default=0.0)
        allowed_ratio = 1.0 + (
            temporal_config.trust_region_tolerance_rad
            / temporal_config.max_joint_step_rad
        )
        if max_ratio > allowed_ratio:
            raise RuntimeError(f"Post-run trust-region audit failed for {name}: {max_ratio}")

        floor_noop_max_abs = None
        if row["contact_policy"] == "floor_motion":
            reference = references[name]
            reference_arrays = {
                "root_pos": np.asarray(reference["root_pos"])[: len(frames)],
                "root_rot": np.asarray(reference["root_rot"])[: len(frames)],
                "dof_pos": np.asarray(reference["dof_pos"])[: len(frames)],
            }
            differences = [
                float(np.max(np.abs(payload[field] - reference_arrays[field])))
                for field in reference_arrays
            ]
            floor_noop_max_abs = max(differences)
            if floor_noop_max_abs != 0.0:
                raise RuntimeError(
                    f"floor_motion semantic no-op failed for {name}: {floor_noop_max_abs}"
                )

        contact_diags = retargeter.contact_frame_diagnostics
        collision_diags = retargeter.collision_frame_diagnostics
        max_root_lift = max(item.applied_root_lift_m for item in contact_diags)
        correction_frames = sum(item.applied_root_lift_m > 0.0 for item in contact_diags)
        contact_frames = sum(
            item.left_human_contact or item.right_human_contact for item in contact_diags
        )
        anchor_frames = sum(item.active_anchor_count > 0 for item in contact_diags)
        output_hash = sha256_file(output_path)
        source_hash = sha256_file(source_bvh)
        full_sequence = len(frames) == source_frame_count
        catalog_rows.append(
            {
                "motion_name": name,
                "pkl_path": str(output_path),
                "source_bvh": str(source_bvh),
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_pair_status": "verified_generated_exact" if full_sequence else "generated_prefix_smoke",
                "pkl_sha256": output_hash,
                "source_bvh_sha256": source_hash,
                "frame_alignment": "exact" if full_sequence else "source_prefix",
                "notes": "Contact-GMR A3; frozen A2 plus source-contact foot anchors and bounded feet_only root lift",
            }
        )
        manifest_inputs.append(
            {
                "motion_name": name,
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_bvh": str(source_bvh),
                "source_bvh_sha256": source_hash,
                "source_fps": source_fps,
                "source_frame_count": source_frame_count,
                "output_frame_count": len(frames),
                "output_pkl": str(output_path),
                "output_pkl_sha256": output_hash,
                "diagnostic_csv": str(diagnostic_path),
                "diagnostic_csv_sha256": sha256_file(diagnostic_path),
                "serialization_roundtrip_exact": True,
                "max_observed_joint_velocity_rad_s": max_velocity,
                "max_observed_trust_region_ratio": max_ratio,
                "trust_region_bound_satisfied": True,
                "minimum_observed_audited_pair_distance_m": min(
                    item.minimum_pair_distance_m for item in collision_diags
                ),
                "human_contact_frame_count": contact_frames,
                "anchor_active_frame_count": anchor_frames,
                "root_correction_frame_count": correction_frames,
                "max_applied_root_lift_m": max_root_lift,
                "max_pre_ground_penetration_m": max(
                    item.pre_max_ground_penetration_m for item in contact_diags
                ),
                "max_post_ground_penetration_m": max(
                    item.post_max_ground_penetration_m for item in contact_diags
                ),
                "floor_motion_noop_max_abs": floor_noop_max_abs,
                "retarget_seconds": elapsed,
            }
        )
        total_frames += len(frames)
        if progress:
            progress(
                f"[{sequence_index}/{len(rows)}] completed {name}: frames={len(frames)}, "
                f"anchors={anchor_frames}, corrected={correction_frames}, "
                f"max_lift={max_root_lift:.6f}, seconds={elapsed:.2f}"
            )

    if formal and total_frames != int(frozen["total_frames"]):
        raise RuntimeError(
            f"Formal Contact-GMR frame count is {total_frames}, expected {frozen['total_frames']}"
        )
    generated_catalog = destination / "contact_motion_catalog.csv"
    with generated_catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(catalog_rows)
    config_file = Path(config["_config_path"])
    source_files = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("contact.py"),
        Path(__file__).resolve().with_name("contact_input_audit.py"),
        Path(__file__).resolve().with_name("contact_cli.py"),
        Path(__file__).resolve().with_name("collision.py"),
        Path(__file__).resolve().with_name("temporal.py"),
    ]
    manifest = {
        "schema_version": 1,
        "experiment": config["experiment_name"],
        "formal_role": config["formal_role"],
        "complete": True,
        "formal_run": formal,
        "elapsed_seconds": time.perf_counter() - run_started,
        "cohort": {
            "source_catalog": str(named_paths["source catalog"]),
            "source_catalog_sha256": sha256_file(named_paths["source catalog"]),
            "a2_reference_catalog": str(named_paths["A2 reference catalog"]),
            "a2_reference_catalog_sha256": sha256_file(named_paths["A2 reference catalog"]),
            "motion_count": len(rows),
            "total_frames": total_frames,
            "max_frames_per_motion": max_frames,
            "requested_motions": sorted(selected),
        },
        "intervention": {
            "temporal_gmr": temporal_config.as_dict(),
            "collision_gmr": collision_config.as_dict(),
            "contact_gmr": contact_config.as_dict(),
        },
        "experiment_config": {"path": str(config_file), "sha256": sha256_file(config_file)},
        "gmr": {
            **git_state,
            "solver": str(config["gmr"]["solver"]),
            "damping": float(config["gmr"]["damping"]),
            "upstream_use_velocity_limit": False,
            "internal_timestep_s": float(retargeter.model.opt.timestep),
        },
        "frozen_artifacts": [
            {"label": label, "path": str(path), "sha256": sha256_file(path)}
            for label, path in named_paths.items()
        ],
        "implementation_sources": [
            {"path": str(path), "sha256": sha256_file(path)} for path in source_files
        ],
        "inputs": manifest_inputs,
        "catalog": {"path": str(generated_catalog), "sha256": sha256_file(generated_catalog)},
    }
    manifest_path = destination / "run_manifest.json"
    _write_json(manifest_path, manifest)
    return TemporalRunResult(
        output_dir=destination,
        catalog_csv=generated_catalog,
        manifest_json=manifest_path,
        motion_count=len(rows),
        frame_count=total_frames,
    )
