"""Headless, hash-audited runner for the frozen Temporal-GMR development cohort."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import pickle
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import mujoco
import numpy as np
import yaml

from .temporal import TemporalGMRConfig, TemporalGeneralMotionRetargeting


CATALOG_COLUMNS = (
    "motion_name",
    "pkl_path",
    "source_bvh",
    "motion_category",
    "contact_policy",
    "source_pair_status",
    "pkl_sha256",
    "source_bvh_sha256",
    "frame_alignment",
    "notes",
)


@dataclass(frozen=True)
class TemporalRunResult:
    output_dir: Path
    catalog_csv: Path
    manifest_json: Path
    motion_count: int
    frame_count: int


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(
            f"Frozen {label} hash mismatch for {path}: expected {expected}, got {actual}"
        )


def _prepare_empty_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Output is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"Output directory must be empty: {path}")
    else:
        path.mkdir(parents=True)


def _write_pickle_atomic(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("wb") as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = [column for column in CATALOG_COLUMNS if column not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"Frozen catalog is missing columns: {missing}")
        rows = list(reader)
    names = [row["motion_name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("Frozen catalog contains duplicate motion names")
    return rows


def _git_state(path: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {"repository_root": str(path), "commit": commit, "dirty": bool(status), "change_count": len(status)}


def _source_fps(path: Path) -> float:
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip().startswith("Frame Time:"):
                frame_time = float(line.split(":", 1)[1].strip())
                if np.isfinite(frame_time) and frame_time > 0.0:
                    return 1.0 / frame_time
    raise ValueError(f"Could not find a positive BVH Frame Time in {path}")


def load_temporal_experiment_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Temporal experiment config must be a schema_version=1 mapping")
    raw["_config_path"] = str(config_path)
    temporal = raw.get("temporal_gmr", {})
    raw["_temporal_config"] = TemporalGMRConfig(**temporal)
    return raw


def _joint_names(model: mujoco.MjModel) -> tuple[str, ...]:
    names: list[str] = []
    for joint_id in range(model.njnt):
        if int(model.jnt_type[joint_id]) == int(mujoco.mjtJoint.mjJNT_FREE):
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if name is None:
            raise ValueError(f"Joint id {joint_id} is unnamed")
        names.append(name)
    return tuple(names)


def run_temporal_retargeting(
    config_path: str | Path,
    output_dir: str | Path,
    *,
    motions: Sequence[str] | None = None,
    max_frames: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> TemporalRunResult:
    config = load_temporal_experiment_config(config_path)
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty_output(destination)
    retargeted_dir = destination / "retargeted"
    diagnostics_dir = destination / "diagnostics"
    retargeted_dir.mkdir()
    diagnostics_dir.mkdir()

    paths = config["paths"]
    frozen = config["frozen_inputs"]
    catalog_path = Path(paths["development_catalog"]).expanduser().resolve()
    gmr_root = Path(paths["gmr_root"]).expanduser().resolve()
    motion_retarget_path = Path(paths["gmr_motion_retarget"]).expanduser().resolve()
    loader_path = Path(paths["gmr_lafan1_loader"]).expanduser().resolve()
    ik_config_path = Path(paths["gmr_ik_config"]).expanduser().resolve()
    robot_xml_path = Path(paths["robot_xml"]).expanduser().resolve()
    for path in (catalog_path, motion_retarget_path, loader_path, ik_config_path, robot_xml_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    _require_hash(catalog_path, frozen["development_catalog_sha256"], "catalog")
    _require_hash(motion_retarget_path, frozen["gmr_motion_retarget_sha256"], "GMR implementation")
    _require_hash(loader_path, frozen["gmr_lafan1_loader_sha256"], "LAFAN1 loader")
    _require_hash(ik_config_path, frozen["gmr_ik_config_sha256"], "IK config")
    _require_hash(robot_xml_path, frozen["robot_xml_sha256"], "robot XML")
    git_state = _git_state(gmr_root)
    if git_state["commit"] != frozen["gmr_commit"]:
        raise ValueError(
            f"GMR commit mismatch: expected {frozen['gmr_commit']}, got {git_state['commit']}"
        )

    rows = _read_catalog(catalog_path)
    selected = set(motions or ())
    if selected:
        available = {row["motion_name"] for row in rows}
        missing = selected - available
        if missing:
            raise ValueError(f"Requested motions are absent from frozen catalog: {sorted(missing)}")
        rows = [row for row in rows if row["motion_name"] in selected]
    if max_frames is not None and max_frames < 1:
        raise ValueError("max_frames must be >= 1")
    is_formal_development_run = not selected and max_frames is None
    if is_formal_development_run:
        expected_count = int(frozen["motion_count"])
        if len(rows) != expected_count:
            raise ValueError(f"Expected {expected_count} development motions, found {len(rows)}")

    from general_motion_retargeting.utils.lafan1 import load_bvh_file

    temporal_config: TemporalGMRConfig = config["_temporal_config"]
    catalog_rows: list[dict[str, str]] = []
    manifest_inputs: list[dict[str, Any]] = []
    total_frames = 0
    run_started = time.perf_counter()
    for sequence_index, row in enumerate(rows, start=1):
        name = row["motion_name"]
        source_bvh = Path(row["source_bvh"]).expanduser().resolve()
        if not source_bvh.is_file():
            raise FileNotFoundError(source_bvh)
        _require_hash(source_bvh, row["source_bvh_sha256"], f"source BVH {name}")
        if progress:
            progress(f"[{sequence_index}/{len(rows)}] Temporal-GMR {name}")
        frames, human_height = load_bvh_file(str(source_bvh), format="lafan1")
        source_frame_count = len(frames)
        if max_frames is not None:
            frames = frames[:max_frames]
        if not frames:
            raise ValueError(f"No frames selected for {name}")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            retargeter = TemporalGeneralMotionRetargeting(
                src_human="bvh_lafan1",
                tgt_robot="unitree_g1",
                actual_human_height=float(human_height),
                solver=str(config["gmr"]["solver"]),
                damping=float(config["gmr"]["damping"]),
                verbose=False,
                temporal_config=temporal_config,
            )
        sequence_started = time.perf_counter()
        qpos = np.empty((len(frames), retargeter.model.nq), dtype=np.float64)
        for frame_index, human_frame in enumerate(frames):
            qpos[frame_index] = retargeter.retarget(human_frame)
        elapsed = time.perf_counter() - sequence_started
        if not np.isfinite(qpos).all():
            raise RuntimeError(f"Temporal-GMR produced non-finite qpos for {name}")
        if qpos.shape[1] != 36:
            raise RuntimeError(f"Expected G1 qpos width 36, got {qpos.shape[1]}")

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
        np.testing.assert_array_equal(roundtrip["root_pos"], payload["root_pos"])
        np.testing.assert_array_equal(roundtrip["root_rot"], payload["root_rot"])
        np.testing.assert_array_equal(roundtrip["dof_pos"], payload["dof_pos"])

        diagnostic_path = diagnostics_dir / f"{name}.csv"
        diagnostic_rows = [asdict(item) for item in retargeter.frame_diagnostics]
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
        if max_ratio > 1.0 + temporal_config.trust_region_tolerance_rad / temporal_config.max_joint_step_rad:
            raise RuntimeError(f"Post-run trust-region audit failed for {name}: ratio={max_ratio}")

        output_hash = sha256_file(output_path)
        source_hash = sha256_file(source_bvh)
        full_sequence = len(frames) == source_frame_count
        pair_status = "verified_generated_exact" if full_sequence else "generated_prefix_smoke"
        alignment = "exact" if full_sequence else "source_prefix"
        note = (
            "Temporal-GMR A1; cumulative 30 Hz joint trust region, previous-output "
            "posture regularization, and soft joint-limit margin; no collision/contact constraint"
        )
        catalog_rows.append(
            {
                "motion_name": name,
                "pkl_path": str(output_path),
                "source_bvh": str(source_bvh),
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_pair_status": pair_status,
                "pkl_sha256": output_hash,
                "source_bvh_sha256": source_hash,
                "frame_alignment": alignment,
                "notes": note,
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
                "retarget_seconds": elapsed,
            }
        )
        total_frames += len(frames)
        if progress:
            progress(
                f"[{sequence_index}/{len(rows)}] completed {name}: frames={len(frames)}, "
                f"max_velocity={max_velocity:.9f}, seconds={elapsed:.2f}"
            )

    generated_catalog = destination / "temporal_motion_catalog.csv"
    with generated_catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(catalog_rows)

    source_files = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("temporal.py"),
        Path(__file__).resolve().with_name("temporal_cli.py"),
    ]
    resolved_config_path = Path(config["_config_path"])
    manifest = {
        "schema_version": 1,
        "experiment": "I0_temporal_gmr_development",
        "complete": True,
        "formal_development_run": is_formal_development_run,
        "elapsed_seconds": time.perf_counter() - run_started,
        "cohort": {
            "source_catalog": str(catalog_path),
            "source_catalog_sha256": sha256_file(catalog_path),
            "motion_count": len(rows),
            "total_frames": total_frames,
            "max_frames_per_motion": max_frames,
            "requested_motions": sorted(selected),
        },
        "intervention": temporal_config.as_dict(),
        "experiment_config": {
            "path": str(resolved_config_path),
            "sha256": sha256_file(resolved_config_path),
        },
        "gmr": {
            **git_state,
            "solver": str(config["gmr"]["solver"]),
            "damping": float(config["gmr"]["damping"]),
            "upstream_use_velocity_limit": False,
            "internal_timestep_s": float(retargeter.model.opt.timestep),
        },
        "frozen_artifacts": [
            {"path": str(path), "sha256": sha256_file(path)}
            for path in (motion_retarget_path, loader_path, ik_config_path, robot_xml_path)
        ],
        "implementation_sources": [
            {"path": str(path), "sha256": sha256_file(path)} for path in source_files
        ],
        "inputs": manifest_inputs,
        "catalog": {
            "path": str(generated_catalog),
            "sha256": sha256_file(generated_catalog),
        },
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
