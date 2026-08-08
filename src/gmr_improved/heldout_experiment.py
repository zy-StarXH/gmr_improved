"""Hash-gated A0/A1 generation for the preregistered Temporal-GMR held-out set."""

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
from typing import Any, Callable, Literal

import mujoco
import numpy as np
import yaml

from general_motion_retargeting import GeneralMotionRetargeting
from general_motion_retargeting.utils.lafan1 import load_bvh_file

from .temporal import TemporalGMRConfig, TemporalGeneralMotionRetargeting


Variant = Literal["a0", "a1"]
SOURCE_COLUMNS = (
    "motion_name",
    "source_bvh",
    "motion_category",
    "contact_policy",
    "source_bvh_sha256",
    "source_frame_count",
    "source_fps",
    "selection_status",
)
QUALITY_CATALOG_COLUMNS = (
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
class HeldoutRunResult:
    variant: Variant
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


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Output directory must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _write_pickle_atomic(payload: dict[str, Any], path: Path) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    with partial.open("wb") as stream:
        pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
    partial.replace(path)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_state(path: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    changes = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return {
        "repository_root": str(path),
        "commit": commit,
        "dirty": bool(changes),
        "change_count": len(changes),
    }


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


def _read_sources(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = sorted(set(SOURCE_COLUMNS) - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"Held-out source catalog is missing columns: {missing}")
        rows = list(reader)
    names = [row["motion_name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("Held-out source catalog contains duplicate names")
    return rows


def load_heldout_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Held-out config must be a schema_version=1 mapping")
    config["_config_path"] = str(config_path)
    config["_temporal_config"] = TemporalGMRConfig(**config["temporal_gmr"])
    return config


def _audit_frozen_inputs(config: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    paths = {name: Path(value).expanduser().resolve() for name, value in config["paths"].items()}
    hashes = config["frozen_hashes"]
    checks = (
        ("gmr_motion_retarget", "gmr_motion_retarget_sha256"),
        ("gmr_lafan1_loader", "gmr_lafan1_loader_sha256"),
        ("gmr_ik_config", "gmr_ik_config_sha256"),
        ("robot_xml", "robot_xml_sha256"),
        ("source_catalog", "source_catalog_sha256"),
        ("frozen_temporal_config", "frozen_temporal_config_sha256"),
        ("frozen_temporal_implementation", "frozen_temporal_implementation_sha256"),
        ("quality_config", "quality_config_sha256"),
    )
    artifacts: list[dict[str, str]] = []
    for path_key, hash_key in checks:
        path = paths[path_key]
        if not path.is_file():
            raise FileNotFoundError(path)
        _require_hash(path, hashes[hash_key], path_key)
        artifacts.append({"path": str(path), "sha256": hashes[hash_key]})
    frozen_temporal = yaml.safe_load(
        paths["frozen_temporal_config"].read_text(encoding="utf-8")
    )["temporal_gmr"]
    if frozen_temporal != config["temporal_gmr"]:
        raise ValueError("Held-out Temporal parameters differ from frozen development v2")
    git = _git_state(paths["gmr_root"])
    if git["commit"] != hashes["gmr_commit"]:
        raise ValueError(
            f"GMR commit mismatch: expected {hashes['gmr_commit']}, got {git['commit']}"
        )
    return artifacts, git


def run_heldout_generation(
    config_path: str | Path,
    output_dir: str | Path,
    variant: Variant,
    *,
    progress: Callable[[str], None] | None = None,
) -> HeldoutRunResult:
    if variant not in {"a0", "a1"}:
        raise ValueError(f"variant must be 'a0' or 'a1', got {variant!r}")
    config = load_heldout_config(config_path)
    artifacts, git = _audit_frozen_inputs(config)
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    motion_dir = destination / "retargeted"
    diagnostic_dir = destination / "diagnostics"
    motion_dir.mkdir()
    if variant == "a1":
        diagnostic_dir.mkdir()

    source_catalog = Path(config["paths"]["source_catalog"]).resolve()
    rows = _read_sources(source_catalog)
    expected = config["experiment"]
    if len(rows) != int(expected["motion_count"]):
        raise ValueError(
            f"Expected {expected['motion_count']} held-out motions, found {len(rows)}"
        )
    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row["motion_category"]] = category_counts.get(row["motion_category"], 0) + 1
    if len(category_counts) != int(expected["categories"]) or any(
        count != int(expected["motions_per_category"]) for count in category_counts.values()
    ):
        raise ValueError(f"Held-out category balance mismatch: {category_counts}")

    temporal_config: TemporalGMRConfig = config["_temporal_config"]
    catalog_rows: list[dict[str, str]] = []
    manifest_inputs: list[dict[str, Any]] = []
    total_frames = 0
    started = time.perf_counter()
    for sequence_index, row in enumerate(rows, start=1):
        name = row["motion_name"]
        source = Path(row["source_bvh"]).resolve()
        _require_hash(source, row["source_bvh_sha256"], f"source BVH {name}")
        if row["selection_status"] != "preregistered_heldout":
            raise ValueError(f"Unexpected selection status for {name}: {row['selection_status']}")
        if progress:
            progress(f"[{sequence_index}/{len(rows)}] {variant.upper()} {name}")
        frames, human_height = load_bvh_file(str(source), format="lafan1")
        expected_frames = int(row["source_frame_count"])
        if len(frames) != expected_frames:
            raise ValueError(
                f"Source frame mismatch for {name}: expected {expected_frames}, got {len(frames)}"
            )
        captured = io.StringIO()
        common = dict(
            src_human="bvh_lafan1",
            tgt_robot="unitree_g1",
            actual_human_height=float(human_height),
            solver=str(config["gmr"]["solver"]),
            damping=float(config["gmr"]["damping"]),
            verbose=False,
        )
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            if variant == "a0":
                retargeter = GeneralMotionRetargeting(
                    **common, use_velocity_limit=False
                )
            else:
                retargeter = TemporalGeneralMotionRetargeting(
                    **common, temporal_config=temporal_config
                )
        sequence_started = time.perf_counter()
        qpos = np.empty((len(frames), retargeter.model.nq), dtype=np.float64)
        for frame_index, human_frame in enumerate(frames):
            qpos[frame_index] = retargeter.retarget(human_frame)
        elapsed = time.perf_counter() - sequence_started
        if qpos.shape != (expected_frames, 36) or not np.isfinite(qpos).all():
            raise RuntimeError(
                f"Invalid {variant.upper()} qpos for {name}: shape={qpos.shape}, "
                f"finite={np.isfinite(qpos).all()}"
            )
        output_path = motion_dir / f"{name}.pkl"
        payload = {
            "fps": float(config["gmr"]["output_fps"]),
            "root_pos": qpos[:, :3],
            "root_rot": qpos[:, 3:7][:, [1, 2, 3, 0]],
            "dof_pos": qpos[:, 7:],
            "dof_names": _joint_names(retargeter.model),
        }
        _write_pickle_atomic(payload, output_path)
        with output_path.open("rb") as stream:
            written = pickle.load(stream)
        for field in ("root_pos", "root_rot", "dof_pos"):
            np.testing.assert_array_equal(written[field], payload[field])

        diagnostic_entry: dict[str, Any] | None = None
        max_velocity: float | None = None
        max_ratio: float | None = None
        if variant == "a1":
            diagnostic_path = diagnostic_dir / f"{name}.csv"
            diagnostic_rows = [asdict(item) for item in retargeter.frame_diagnostics]
            if len(diagnostic_rows) != expected_frames:
                raise RuntimeError(f"A1 diagnostic frame mismatch for {name}")
            with diagnostic_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(diagnostic_rows[0]))
                writer.writeheader()
                writer.writerows(diagnostic_rows)
            constrained = [item for item in retargeter.frame_diagnostics if item.trust_region_enabled]
            max_velocity = max(
                (item.max_joint_velocity_rad_s or 0.0 for item in constrained), default=0.0
            )
            max_ratio = max(
                (item.max_trust_region_ratio or 0.0 for item in constrained), default=0.0
            )
            if max_ratio > 1.0 + 1e-6:
                raise RuntimeError(f"A1 trust-region audit failed for {name}: {max_ratio}")
            diagnostic_entry = {
                "path": str(diagnostic_path),
                "sha256": sha256_file(diagnostic_path),
                "frame_count": len(diagnostic_rows),
            }

        output_hash = sha256_file(output_path)
        note = (
            "Preregistered held-out A0 original GMR; full source sequence; "
            "use_velocity_limit=false"
            if variant == "a0"
            else "Preregistered held-out A1 Temporal-GMR v2; frozen after development; full source sequence"
        )
        catalog_rows.append(
            {
                "motion_name": name,
                "pkl_path": str(output_path),
                "source_bvh": str(source),
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_pair_status": "verified_generated_exact",
                "pkl_sha256": output_hash,
                "source_bvh_sha256": row["source_bvh_sha256"],
                "frame_alignment": "exact",
                "notes": note,
            }
        )
        manifest_inputs.append(
            {
                "motion_name": name,
                "motion_category": row["motion_category"],
                "contact_policy": row["contact_policy"],
                "source_bvh": str(source),
                "source_bvh_sha256": row["source_bvh_sha256"],
                "source_frame_count": expected_frames,
                "output_pkl": str(output_path),
                "output_pkl_sha256": output_hash,
                "output_frame_count": int(qpos.shape[0]),
                "serialization_roundtrip_exact": True,
                "diagnostic": diagnostic_entry,
                "max_observed_joint_velocity_rad_s": max_velocity,
                "max_observed_trust_region_ratio": max_ratio,
                "retarget_seconds": elapsed,
            }
        )
        total_frames += expected_frames
        if progress:
            suffix = (
                f", max_velocity={max_velocity:.9f}" if max_velocity is not None else ""
            )
            progress(
                f"[{sequence_index}/{len(rows)}] completed {name}: "
                f"frames={expected_frames}{suffix}, seconds={elapsed:.2f}"
            )

    if total_frames != int(expected["total_frames"]):
        raise RuntimeError(
            f"Held-out frame total mismatch: expected {expected['total_frames']}, got {total_frames}"
        )
    catalog_path = destination / f"heldout_{variant}_quality_catalog.csv"
    with catalog_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUALITY_CATALOG_COLUMNS)
        writer.writeheader()
        writer.writerows(catalog_rows)

    runner_path = Path(__file__).resolve()
    config_file = Path(config["_config_path"])
    manifest = {
        "schema_version": 1,
        "experiment": "I0_temporal_gmr_preregistered_heldout",
        "variant": variant,
        "complete": True,
        "results_unblinded_after_generation": True,
        "cohort": {
            "source_catalog": str(source_catalog),
            "source_catalog_sha256": sha256_file(source_catalog),
            "motion_count": len(rows),
            "total_frames": total_frames,
            "category_counts": category_counts,
        },
        "generator": {
            "runner_path": str(runner_path),
            "runner_sha256": sha256_file(runner_path),
            "config_path": str(config_file),
            "config_sha256": sha256_file(config_file),
            "gmr": git,
            "solver": config["gmr"]["solver"],
            "damping": config["gmr"]["damping"],
            "upstream_use_velocity_limit": False,
            "temporal_parameters": (
                temporal_config.as_dict() if variant == "a1" else None
            ),
        },
        "frozen_artifacts": artifacts,
        "inputs": manifest_inputs,
        "catalog": {"path": str(catalog_path), "sha256": sha256_file(catalog_path)},
        "elapsed_seconds": time.perf_counter() - started,
    }
    manifest_path = destination / "run_manifest.json"
    _write_json(manifest_path, manifest)
    return HeldoutRunResult(
        variant=variant,
        output_dir=destination,
        catalog_csv=catalog_path,
        manifest_json=manifest_path,
        motion_count=len(rows),
        frame_count=total_frames,
    )

