"""Hash-gated development runner for A2 Collision-GMR."""

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

from .collision import (
    CollisionGMRConfig,
    CollisionGeneralMotionRetargeting,
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


def load_collision_experiment_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Collision experiment config must be a schema_version=1 mapping")
    temporal = dict(raw.get("temporal_gmr", {}))
    collision = dict(raw.get("collision_gmr", {}))
    if "hand_patterns" in collision:
        collision["hand_patterns"] = tuple(collision["hand_patterns"])
    raw["_config_path"] = str(config_path)
    raw["_temporal_config"] = TemporalGMRConfig(**temporal)
    raw["_collision_config"] = CollisionGMRConfig(**collision)
    return raw


def _verify_collision_audit(path: Path, collision_config: CollisionGMRConfig) -> dict[str, Any]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    model_equivalence = audit.get("model_equivalence", {})
    pair_audit = audit.get("pair_audit", {})
    if not model_equivalence.get("ok") or model_equivalence.get("mismatch_count") != 0:
        raise ValueError("Collision model equivalence audit is not passing")
    if pair_audit.get("included_geom_pair_count") != collision_config.expected_pair_count:
        raise ValueError("Collision audit pair count differs from runtime config")
    if pair_audit.get("below_minimum_at_neutral_count") != 0:
        raise ValueError("Collision model begins below the preregistered minimum distance")
    parameters = pair_audit.get("parameters", {})
    expected = {
        "minimum_distance_m": collision_config.minimum_distance_m,
        "detection_distance_m": collision_config.detection_distance_m,
        "gain": collision_config.gain,
        "bound_relaxation": collision_config.bound_relaxation,
        "broadphase": collision_config.broadphase,
        "minimum_tree_distance": collision_config.minimum_tree_distance,
    }
    for key, value in expected.items():
        if parameters.get(key) != value:
            raise ValueError(f"Collision audit parameter mismatch for {key}")
    if tuple(parameters.get("hand_patterns", ())) != collision_config.hand_patterns:
        raise ValueError("Collision audit hand patterns differ from runtime config")
    return audit


def run_collision_retargeting(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    motions: Sequence[str] | None = None,
    max_frames: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> TemporalRunResult:
    config = load_collision_experiment_config(config_path)
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty_output(destination)
    retargeted_dir = destination / "retargeted"
    diagnostics_dir = destination / "diagnostics"
    retargeted_dir.mkdir()
    diagnostics_dir.mkdir()

    paths = config["paths"]
    frozen = config["frozen_inputs"]
    named_paths = {
        "development catalog": Path(paths["development_catalog"]).expanduser().resolve(),
        "GMR implementation": Path(paths["gmr_motion_retarget"]).expanduser().resolve(),
        "LAFAN1 loader": Path(paths["gmr_lafan1_loader"]).expanduser().resolve(),
        "IK config": Path(paths["gmr_ik_config"]).expanduser().resolve(),
        "original robot XML": Path(paths["original_robot_xml"]).expanduser().resolve(),
        "derived robot XML": Path(paths["derived_robot_xml"]).expanduser().resolve(),
        "collision pair CSV": Path(paths["collision_pairs_csv"]).expanduser().resolve(),
        "collision model audit": Path(paths["collision_model_audit"]).expanduser().resolve(),
        "Temporal-GMR implementation": Path(paths["temporal_implementation"]).expanduser().resolve(),
        "Temporal-GMR experiment implementation": Path(paths["temporal_experiment_implementation"]).expanduser().resolve(),
        "Temporal-GMR v2 config": Path(paths["temporal_v2_config"]).expanduser().resolve(),
        "collision implementation": Path(paths["collision_implementation"]).expanduser().resolve(),
        "collision model implementation": Path(paths["collision_model_implementation"]).expanduser().resolve(),
        "collision experiment implementation": Path(paths["collision_experiment_implementation"]).expanduser().resolve(),
        "collision CLI implementation": Path(paths["collision_cli_implementation"]).expanduser().resolve(),
    }
    hash_keys = {
        "development catalog": "development_catalog_sha256",
        "GMR implementation": "gmr_motion_retarget_sha256",
        "LAFAN1 loader": "gmr_lafan1_loader_sha256",
        "IK config": "gmr_ik_config_sha256",
        "original robot XML": "original_robot_xml_sha256",
        "derived robot XML": "derived_robot_xml_sha256",
        "collision pair CSV": "collision_pairs_csv_sha256",
        "collision model audit": "collision_model_audit_sha256",
        "Temporal-GMR implementation": "temporal_implementation_sha256",
        "Temporal-GMR experiment implementation": "temporal_experiment_implementation_sha256",
        "Temporal-GMR v2 config": "temporal_v2_config_sha256",
        "collision implementation": "collision_implementation_sha256",
        "collision model implementation": "collision_model_implementation_sha256",
        "collision experiment implementation": "collision_experiment_implementation_sha256",
        "collision CLI implementation": "collision_cli_implementation_sha256",
    }
    for label, path in named_paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        _require_hash(path, frozen[hash_keys[label]], label)

    collision_config: CollisionGMRConfig = config["_collision_config"]
    temporal_config: TemporalGMRConfig = config["_temporal_config"]
    _verify_collision_audit(named_paths["collision model audit"], collision_config)
    gmr_root = Path(paths["gmr_root"]).expanduser().resolve()
    git_state = _git_state(gmr_root)
    if git_state["commit"] != frozen["gmr_commit"]:
        raise ValueError(
            f"GMR commit mismatch: expected {frozen['gmr_commit']}, got {git_state['commit']}"
        )

    rows = _read_catalog(named_paths["development catalog"])
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
        raise ValueError("Formal Collision-GMR run does not contain the frozen motion count")

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
            progress(f"[{sequence_index}/{len(rows)}] Collision-GMR {name}")
        frames, human_height = load_bvh_file(str(source_bvh), format="lafan1")
        source_frame_count = len(frames)
        if max_frames is not None:
            frames = frames[:max_frames]
        if not frames:
            raise ValueError(f"No frames selected for {name}")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            retargeter = CollisionGeneralMotionRetargeting(
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
            )
        sequence_started = time.perf_counter()
        qpos = np.empty((len(frames), retargeter.model.nq), dtype=np.float64)
        for frame_index, human_frame in enumerate(frames):
            qpos[frame_index] = retargeter.retarget(human_frame)
        elapsed = time.perf_counter() - sequence_started
        if qpos.shape != (len(frames), 36) or not np.isfinite(qpos).all():
            raise RuntimeError(f"Invalid Collision-GMR qpos for {name}: {qpos.shape}")

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

        if len(retargeter.frame_diagnostics) != len(frames) or len(
            retargeter.collision_frame_diagnostics
        ) != len(frames):
            raise RuntimeError(f"Diagnostic frame mismatch for {name}")
        diagnostic_rows: list[dict[str, Any]] = []
        for temporal_item, collision_item in zip(
            retargeter.frame_diagnostics,
            retargeter.collision_frame_diagnostics,
            strict=True,
        ):
            temporal_row = asdict(temporal_item)
            collision_row = asdict(collision_item)
            if temporal_row["frame_index"] != collision_row.pop("frame_index"):
                raise RuntimeError("Temporal/collision diagnostic frame index mismatch")
            temporal_row.update(
                {f"collision_{key}": value for key, value in collision_row.items()}
            )
            diagnostic_rows.append(temporal_row)
        diagnostic_path = diagnostics_dir / f"{name}.csv"
        with diagnostic_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(diagnostic_rows[0]))
            writer.writeheader()
            writer.writerows(diagnostic_rows)

        constrained = [item for item in retargeter.frame_diagnostics if item.trust_region_enabled]
        max_ratio = max(
            (item.max_trust_region_ratio or 0.0 for item in constrained), default=0.0
        )
        max_velocity = max(
            (item.max_joint_velocity_rad_s or 0.0 for item in constrained), default=0.0
        )
        allowed_ratio = 1.0 + (
            temporal_config.trust_region_tolerance_rad / temporal_config.max_joint_step_rad
        )
        if max_ratio > allowed_ratio:
            raise RuntimeError(f"Post-run trust-region audit failed for {name}: {max_ratio}")
        collision_diags = retargeter.collision_frame_diagnostics
        min_distance = min(item.minimum_pair_distance_m for item in collision_diags)
        max_active = max(item.active_pair_count for item in collision_diags)
        max_below = max(item.below_minimum_pair_count for item in collision_diags)
        max_penetrating = max(item.penetrating_pair_count for item in collision_diags)

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
                "notes": "Collision-GMR A2; frozen Temporal-GMR v2 plus audited tree-distance>=3 non-hand collision pairs",
            }
        )
        manifest_inputs.append(
            {
                "motion_name": name,
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_bvh": str(source_bvh),
                "source_bvh_sha256": source_hash,
                "source_fps": _source_fps(source_bvh),
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
                "minimum_observed_audited_pair_distance_m": min_distance,
                "max_active_collision_pair_count": max_active,
                "max_below_minimum_pair_count": max_below,
                "max_penetrating_pair_count": max_penetrating,
                "retarget_seconds": elapsed,
            }
        )
        total_frames += len(frames)
        if progress:
            progress(
                f"[{sequence_index}/{len(rows)}] completed {name}: frames={len(frames)}, "
                f"max_velocity={max_velocity:.9f}, min_pair_distance={min_distance:.6f}, "
                f"seconds={elapsed:.2f}"
            )

    generated_catalog = destination / "collision_motion_catalog.csv"
    with generated_catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(catalog_rows)
    config_file = Path(config["_config_path"])
    source_files = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("collision.py"),
        Path(__file__).resolve().with_name("collision_model.py"),
        Path(__file__).resolve().with_name("collision_cli.py"),
        Path(__file__).resolve().with_name("temporal.py"),
        Path(__file__).resolve().with_name("temporal_experiment.py"),
    ]
    manifest = {
        "schema_version": 1,
        "experiment": "I1_collision_gmr_development",
        "complete": True,
        "formal_development_run": formal,
        "elapsed_seconds": time.perf_counter() - run_started,
        "cohort": {
            "source_catalog": str(named_paths["development catalog"]),
            "source_catalog_sha256": sha256_file(named_paths["development catalog"]),
            "motion_count": len(rows),
            "total_frames": total_frames,
            "max_frames_per_motion": max_frames,
            "requested_motions": sorted(selected),
        },
        "intervention": {
            "temporal_gmr": temporal_config.as_dict(),
            "collision_gmr": collision_config.as_dict(),
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
