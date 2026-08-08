"""Independent signed-distance audit of A1/A2 trajectories on frozen geom pairs."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import pandas as pd

from .collision import CollisionGMRConfig, load_audited_geom_pairs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Geometry audit output must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _count_rising_edges(current: np.ndarray, previous: np.ndarray) -> int:
    return int(np.count_nonzero(current & ~previous))


def _load_qpos(path: Path, nq: int) -> np.ndarray:
    with path.open("rb") as stream:
        payload = pickle.load(stream)
    root_pos = np.asarray(payload["root_pos"], dtype=np.float64)
    root_rot_xyzw = np.asarray(payload["root_rot"], dtype=np.float64)
    dof_pos = np.asarray(payload["dof_pos"], dtype=np.float64)
    if (
        root_pos.ndim != 2
        or root_pos.shape[1] != 3
        or root_rot_xyzw.shape != (len(root_pos), 4)
        or dof_pos.shape != (len(root_pos), nq - 7)
    ):
        raise ValueError(f"Invalid motion arrays in {path}")
    qpos = np.empty((len(root_pos), nq), dtype=np.float64)
    qpos[:, :3] = root_pos
    qpos[:, 3:7] = root_rot_xyzw[:, [3, 0, 1, 2]]
    qpos[:, 7:] = dof_pos
    if not np.isfinite(qpos).all():
        raise ValueError(f"Non-finite qpos in {path}")
    return qpos


def _audit_motion(
    path: Path,
    model: mujoco.MjModel,
    data: mujoco.MjData,
    pairs: tuple[tuple[int, int], ...],
    config: CollisionGMRConfig,
) -> dict[str, Any]:
    qpos = _load_qpos(path, model.nq)
    pair_array = np.asarray(pairs, dtype=np.int64)
    geom_a = pair_array[:, 0]
    geom_b = pair_array[:, 1]
    previous_below = np.zeros(len(pairs), dtype=bool)
    previous_penetrating = np.zeros(len(pairs), dtype=bool)
    metrics = {
        "active_frame_count": 0,
        "below_minimum_frame_count": 0,
        "penetrating_frame_count": 0,
        "active_pair_frame_count": 0,
        "below_minimum_pair_frame_count": 0,
        "penetrating_pair_frame_count": 0,
        "below_minimum_pair_event_count": 0,
        "penetrating_pair_event_count": 0,
    }
    minimum = config.detection_distance_m
    fromto = np.empty(6, dtype=np.float64)
    for values in qpos:
        data.qpos[:] = values
        mujoco.mj_forward(model, data)
        delta = data.geom_xpos[geom_a] - data.geom_xpos[geom_b]
        center_distance_sq = np.einsum("ij,ij->i", delta, delta)
        bound = (
            model.geom_rbound[geom_a]
            + model.geom_rbound[geom_b]
            + config.detection_distance_m
        )
        candidates = np.flatnonzero(center_distance_sq <= bound * bound)
        distances = np.full(len(pairs), config.detection_distance_m, dtype=np.float64)
        for pair_index in candidates:
            first, second = pairs[int(pair_index)]
            distances[pair_index] = mujoco.mj_geomDistance(
                model,
                data,
                first,
                second,
                config.detection_distance_m,
                fromto,
            )
        active = distances < config.detection_distance_m - 1e-12
        below = distances < config.minimum_distance_m
        penetrating = distances < 0.0
        metrics["active_frame_count"] += int(active.any())
        metrics["below_minimum_frame_count"] += int(below.any())
        metrics["penetrating_frame_count"] += int(penetrating.any())
        metrics["active_pair_frame_count"] += int(active.sum())
        metrics["below_minimum_pair_frame_count"] += int(below.sum())
        metrics["penetrating_pair_frame_count"] += int(penetrating.sum())
        metrics["below_minimum_pair_event_count"] += _count_rising_edges(
            below, previous_below
        )
        metrics["penetrating_pair_event_count"] += _count_rising_edges(
            penetrating, previous_penetrating
        )
        previous_below = below
        previous_penetrating = penetrating
        minimum = min(minimum, float(distances.min()))
    metrics.update(
        {
            "num_frames": len(qpos),
            "minimum_pair_distance_m": minimum,
            "below_minimum_frame_rate": metrics["below_minimum_frame_count"] / len(qpos),
            "penetrating_frame_rate": metrics["penetrating_frame_count"] / len(qpos),
            "pkl_sha256": _sha256(path),
        }
    )
    return metrics


def audit_collision_geometry(
    derived_xml: str | Path,
    collision_pairs_csv: str | Path,
    a1_dir: str | Path,
    a2_dir: str | Path,
    output_dir: str | Path,
    *,
    config: CollisionGMRConfig | None = None,
) -> Path:
    xml_path = Path(derived_xml).expanduser().resolve()
    pair_path = Path(collision_pairs_csv).expanduser().resolve()
    a1_path = Path(a1_dir).expanduser().resolve()
    a2_path = Path(a2_dir).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    _prepare_empty(destination)
    parameters = config or CollisionGMRConfig()
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    data = mujoco.MjData(model)
    pairs = load_audited_geom_pairs(pair_path, model, parameters)
    a1_files = {path.stem: path for path in a1_path.glob("*.pkl")}
    a2_files = {path.stem: path for path in a2_path.glob("*.pkl")}
    if not a1_files or set(a1_files) != set(a2_files):
        raise ValueError("A1/A2 PKL motion-name sets are empty or unequal")

    rows = []
    for motion_name in sorted(a1_files):
        a1 = _audit_motion(a1_files[motion_name], model, data, pairs, parameters)
        a2 = _audit_motion(a2_files[motion_name], model, data, pairs, parameters)
        if a1["num_frames"] != a2["num_frames"]:
            raise ValueError(f"A1/A2 frame mismatch for {motion_name}")
        row: dict[str, Any] = {"motion_name": motion_name}
        for metric in a1:
            row[f"a1_{metric}"] = a1[metric]
            row[f"a2_{metric}"] = a2[metric]
            if metric != "pkl_sha256":
                row[f"delta_{metric}"] = a2[metric] - a1[metric]
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(destination / "paired_geometry_metrics.csv", index=False)

    count_metrics = (
        "active_frame_count",
        "below_minimum_frame_count",
        "penetrating_frame_count",
        "active_pair_frame_count",
        "below_minimum_pair_frame_count",
        "penetrating_pair_frame_count",
        "below_minimum_pair_event_count",
        "penetrating_pair_event_count",
    )
    totals = {}
    for metric in count_metrics:
        a1_value = int(table[f"a1_{metric}"].sum())
        a2_value = int(table[f"a2_{metric}"].sum())
        totals[metric] = {"a1": a1_value, "a2": a2_value, "delta": a2_value - a1_value}
    frame_count = int(table["a1_num_frames"].sum())
    for count_metric, rate_name in (
        ("below_minimum_frame_count", "below_minimum_frame_rate"),
        ("penetrating_frame_count", "penetrating_frame_rate"),
    ):
        totals[rate_name] = {
            "a1": totals[count_metric]["a1"] / frame_count,
            "a2": totals[count_metric]["a2"] / frame_count,
            "delta": totals[count_metric]["delta"] / frame_count,
        }
    result = {
        "schema_version": 1,
        "motion_count": len(table),
        "frame_count": frame_count,
        "audited_geom_pair_count": len(pairs),
        "parameters": parameters.as_dict(),
        "totals": totals,
        "minimum_pair_distance_m": {
            "a1": float(table["a1_minimum_pair_distance_m"].min()),
            "a2": float(table["a2_minimum_pair_distance_m"].min()),
        },
        "inputs": {
            "derived_xml": {"path": str(xml_path), "sha256": _sha256(xml_path)},
            "collision_pairs_csv": {"path": str(pair_path), "sha256": _sha256(pair_path)},
            "a1_dir": str(a1_path),
            "a2_dir": str(a2_path),
        },
        "interpretation_boundary": (
            "Signed distances are queried only for the preregistered 362 geom pairs. "
            "This is independent of MuJoCo contact-event aggregation and does not cover "
            "excluded hands or body-tree distance below three."
        ),
    }
    output = destination / "geometry_audit_summary.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "complete": True,
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "files": [
            {"path": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in sorted(destination.iterdir())
            if path.name != "audit_manifest.json"
        ],
    }
    (destination / "audit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
