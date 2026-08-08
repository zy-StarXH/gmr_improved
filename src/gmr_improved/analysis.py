from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import pickle
import platform
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/gmr_improved_matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np
import pandas as pd
import yaml


ANALYSIS_VERSION = "step3_failure_analysis_v1.1"


@dataclass(frozen=True)
class AnalysisResult:
    output_dir: Path
    manifest: Path
    evidence_summary: Path
    case_catalog: Path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("baseline analysis config must have schema_version: 1")
    config["_config_path"] = str(config_path)
    return config


def _prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Output path is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"Output directory must be empty: {path}")
    else:
        path.mkdir(parents=True)


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    unknown = ~normalized.isin(["true", "false"])
    if unknown.any():
        values = sorted(normalized.loc[unknown].unique().tolist())
        raise ValueError(f"Invalid boolean values: {values}")
    return normalized.eq("true")


def _json_list(value: Any) -> list[Any]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    parsed = json.loads(str(value))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON list, got: {value!r}")
    return parsed


def _run_read_only(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _audit_inputs(config: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = {key: Path(value).expanduser().resolve() for key, value in config["paths"].items()}
    required_files = (
        "catalog",
        "quality_summary",
        "quality_events",
        "evaluator_config",
        "gmr_core",
        "ik_config",
        "robot_xml",
    )
    for key in required_files:
        if not paths[key].is_file():
            raise FileNotFoundError(f"Missing frozen input {key}: {paths[key]}")
        actual = sha256_file(paths[key])
        expected = config["expected"]["sha256"][key]
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch for {key}: expected {expected}, got {actual}")

    catalog = pd.read_csv(paths["catalog"])
    summary = pd.read_csv(paths["quality_summary"])
    events = pd.read_csv(paths["quality_events"])
    expected = config["expected"]
    if len(catalog) != expected["motion_count"] or len(summary) != expected["motion_count"]:
        raise ValueError("Frozen motion count does not match config")
    if catalog["motion_name"].duplicated().any() or summary["motion_name"].duplicated().any():
        raise ValueError("Motion names must be unique")
    if set(catalog["motion_name"]) != set(summary["motion_name"]):
        raise ValueError("Catalog and summary motion sets differ")
    if set(catalog["source_pair_status"]) != {expected["source_pair_status"]}:
        raise ValueError("Not all source-motion pairs are exactly verified")
    counts = catalog["motion_category"].value_counts().sort_index().to_dict()
    if counts != dict(sorted(expected["strata"].items())):
        raise ValueError(f"Unexpected stratum counts: {counts}")
    if int(summary["num_frames"].sum()) != expected["total_frames"]:
        raise ValueError("Summary total frame count differs from frozen expectation")

    gmr_root = paths["gmr_root"]
    commit = _run_read_only(["git", "rev-parse", "HEAD"], gmr_root)
    if commit != expected["gmr_commit"]:
        raise ValueError(f"GMR commit mismatch: expected {expected['gmr_commit']}, got {commit}")
    worktree_status = _run_read_only(["git", "status", "--short"], gmr_root).splitlines()

    audit = {
        "analysis_version": ANALYSIS_VERSION,
        "checked_at": datetime.now().astimezone().isoformat(),
        "motion_count": int(len(summary)),
        "total_frames": int(summary["num_frames"].sum()),
        "stratum_counts": counts,
        "all_source_pairs_exact": True,
        "gmr_commit": commit,
        "gmr_worktree_status_at_analysis": worktree_status,
        "input_files": {
            key: {"path": str(paths[key]), "sha256": sha256_file(paths[key])}
            for key in required_files
        },
    }
    return audit, catalog, summary, events


def _load_frame_metrics(
    config: dict[str, Any], catalog: pd.DataFrame, summary: pd.DataFrame
) -> pd.DataFrame:
    frame_dir = Path(config["paths"]["evaluation_dir"]).expanduser().resolve() / "frame_metrics"
    tables: list[pd.DataFrame] = []
    frames_by_motion = summary.set_index("motion_name")["num_frames"].astype(int).to_dict()
    for name in catalog["motion_name"]:
        path = frame_dir / f"{name}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Missing frame metrics: {path}")
        table = pd.read_csv(path)
        if len(table) != frames_by_motion[name]:
            raise ValueError(f"Frame count mismatch for {name}: {len(table)} != {frames_by_motion[name]}")
        if set(table["motion_name"].astype(str)) != {name}:
            raise ValueError(f"Unexpected motion_name values in {path}")
        tables.append(table)
    frames = pd.concat(tables, ignore_index=True)
    if len(frames) != config["expected"]["total_frames"]:
        raise ValueError("Concatenated frame total differs from frozen expectation")
    if frames[["frame", "time_s"]].isna().any().any():
        raise ValueError("Frame index/time contains missing values")
    if not np.isfinite(frames[["frame", "time_s"]].to_numpy(dtype=float)).all():
        raise ValueError("Frame index/time contains NaN/Inf")
    return frames


def _metric_masks(config: dict[str, Any], frames: pd.DataFrame) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {}
    for spec in config["analysis"]["metrics"]:
        if "frame_flag" in spec:
            masks[spec["name"]] = _as_bool(frames[spec["frame_flag"]])
        else:
            combined = pd.Series(False, index=frames.index)
            for field in spec["frame_flag_any"]:
                combined |= _as_bool(frames[field])
            masks[spec["name"]] = combined
    return masks


def _motion_summary(
    config: dict[str, Any], catalog: pd.DataFrame, frames: pd.DataFrame, masks: dict[str, pd.Series]
) -> pd.DataFrame:
    meta = catalog.set_index("motion_name")[["motion_category", "contact_policy", "pkl_path", "source_bvh"]]
    rows: list[dict[str, Any]] = []
    specifications = {spec["name"]: spec for spec in config["analysis"]["metrics"]}
    for name, group in frames.groupby("motion_name", sort=False):
        idx = group.index
        row: dict[str, Any] = {
            "motion_name": name,
            "motion_category": meta.loc[name, "motion_category"],
            "contact_policy": meta.loc[name, "contact_policy"],
            "pkl_path": meta.loc[name, "pkl_path"],
            "source_bvh": meta.loc[name, "source_bvh"],
            "num_frames": int(len(group)),
            "duration_s": float(len(group) / config["expected"]["fps"]),
        }
        for metric, mask in masks.items():
            count = int(mask.loc[idx].sum())
            excluded = int(specifications[metric].get("excluded_leading_frames_from_rate", 0))
            eligible = len(group) - excluded
            if eligible <= 0:
                raise ValueError(f"No eligible frames for {metric} in {name}")
            row[f"{metric}_frame_count"] = count
            row[f"{metric}_eligible_frame_count"] = eligible
            row[f"{metric}_frame_rate"] = count / eligible
        rows.append(row)
    return pd.DataFrame(rows)


def _stratum_summary(motions: pd.DataFrame, metrics: Iterable[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [("all", motions)] + [
        (str(name), group) for name, group in motions.groupby("motion_category", sort=True)
    ]
    for scope, group in scopes:
        row: dict[str, Any] = {
            "scope": scope,
            "motion_count": int(len(group)),
            "total_frames": int(group["num_frames"].sum()),
        }
        for metric in metrics:
            counts = group[f"{metric}_frame_count"]
            eligible = group[f"{metric}_eligible_frame_count"]
            rates = group[f"{metric}_frame_rate"]
            row[f"{metric}_affected_motion_count"] = int((counts > 0).sum())
            row[f"{metric}_frame_count"] = int(counts.sum())
            row[f"{metric}_eligible_frame_count"] = int(eligible.sum())
            row[f"{metric}_pooled_frame_rate"] = float(counts.sum() / eligible.sum())
            row[f"{metric}_motion_rate_median"] = float(rates.median())
            row[f"{metric}_motion_rate_min"] = float(rates.min())
            row[f"{metric}_motion_rate_max"] = float(rates.max())
        rows.append(row)
    return pd.DataFrame(rows)


def _event_burden(events: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    categories = catalog.set_index("motion_name")["motion_category"].to_dict()
    table = events.copy()
    table["motion_category"] = table["motion_name"].map(categories)
    rows: list[dict[str, Any]] = []
    scopes = [("all", table)] + [
        (str(name), group) for name, group in table.groupby("motion_category", sort=True)
    ]
    for scope, group in scopes:
        for event_type, subset in group.groupby("event_type", sort=True):
            rows.append(
                {
                    "scope": scope,
                    "event_type": event_type,
                    "event_count": int(len(subset)),
                    "affected_motion_count": int(subset["motion_name"].nunique()),
                    "summed_event_frame_count_with_overlap": int(
                        (subset["end_frame"] - subset["start_frame"] + 1).sum()
                    ),
                    "summed_duration_s_with_overlap": float(subset["duration_s"].sum()),
                    "max_severity": float(subset["max_severity"].max()),
                }
            )
    return pd.DataFrame(rows)


def _joint_hotspots(frames: pd.DataFrame) -> pd.DataFrame:
    definitions = (
        ("near_limit_2pct", "near_limit_2pct_flag", "nearest_limit_joint"),
        ("joint_jump", "joint_jump_flag", "max_joint_step_joint"),
        ("velocity_violation", "velocity_violation_flag", "max_joint_vel_joint"),
    )
    rows: list[dict[str, Any]] = []
    for issue, flag, entity in definitions:
        subset = frames.loc[_as_bool(frames[flag])]
        counts = subset[entity].value_counts()
        for rank, (name, count) in enumerate(counts.items(), start=1):
            rows.append(
                {
                    "issue": issue,
                    "rank": rank,
                    "joint": name,
                    "flagged_frame_count_as_worst_or_nearest": int(count),
                    "fraction_within_issue": float(count / len(subset)),
                }
            )
    return pd.DataFrame(rows)


def _body_tree_distances(xml_path: Path) -> dict[tuple[str, str], int]:
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    names = {
        body_id: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        for body_id in range(model.nbody)
    }
    by_name = {name: body_id for body_id, name in names.items() if name}

    def ancestors(body_id: int) -> dict[int, int]:
        result = {body_id: 0}
        distance = 0
        while body_id != 0:
            body_id = int(model.body_parentid[body_id])
            distance += 1
            result[body_id] = distance
        return result

    distances: dict[tuple[str, str], int] = {}
    for left, left_id in by_name.items():
        left_ancestors = ancestors(left_id)
        for right, right_id in by_name.items():
            right_ancestors = ancestors(right_id)
            common = set(left_ancestors) & set(right_ancestors)
            distances[(left, right)] = min(
                left_ancestors[node] + right_ancestors[node] for node in common
            )
    return distances


def _collision_hotspots(events: pd.DataFrame, robot_xml: Path) -> pd.DataFrame:
    distances = _body_tree_distances(robot_xml)
    subset = events.loc[events["event_type"] == "SELF_COLLISION_NONHAND"].copy()
    rows: list[dict[str, Any]] = []
    for _, event in subset.iterrows():
        entities = _json_list(event["entities"])
        if len(entities) != 2:
            continue
        pair = tuple(sorted(str(value) for value in entities))
        rows.append(
            {
                "motion_name": event["motion_name"],
                "body_a": pair[0],
                "body_b": pair[1],
                "event_frame_count": int(event["end_frame"] - event["start_frame"] + 1),
                "duration_s": float(event["duration_s"]),
                "max_severity_m": float(event["max_severity"]),
                "kinematic_tree_distance": distances.get(pair),
            }
        )
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    grouped = (
        raw.groupby(["body_a", "body_b", "kinematic_tree_distance"], dropna=False)
        .agg(
            event_count=("motion_name", "size"),
            affected_motion_count=("motion_name", "nunique"),
            summed_event_frame_count_with_overlap=("event_frame_count", "sum"),
            summed_duration_s_with_overlap=("duration_s", "sum"),
            max_severity_m=("max_severity_m", "max"),
        )
        .reset_index()
    )
    grouped["structural_overlap_review_required"] = grouped["kinematic_tree_distance"].le(2)
    return grouped.sort_values(
        ["affected_motion_count", "summed_event_frame_count_with_overlap", "max_severity_m"],
        ascending=False,
    ).reset_index(drop=True)


def _body_hotspots(frames: pd.DataFrame, field: str, issue: str) -> pd.DataFrame:
    counts: Counter[str] = Counter()
    motion_sets: dict[str, set[str]] = {}
    for _, row in frames.iterrows():
        for body in _json_list(row[field]):
            body = str(body)
            counts[body] += 1
            motion_sets.setdefault(body, set()).add(str(row["motion_name"]))
    total = sum(counts.values())
    return pd.DataFrame(
        [
            {
                "issue": issue,
                "rank": rank,
                "body": body,
                "body_flagged_frame_count": count,
                "affected_motion_count": len(motion_sets[body]),
                "fraction_of_body_mentions": count / total if total else 0.0,
            }
            for rank, (body, count) in enumerate(counts.most_common(), start=1)
        ]
    )


def _overlap_table(masks: dict[str, pd.Series]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for left_name, left in masks.items():
        for right_name, right in masks.items():
            intersection = int((left & right).sum())
            union = int((left | right).sum())
            left_count = int(left.sum())
            rows.append(
                {
                    "condition": left_name,
                    "outcome": right_name,
                    "condition_frame_count": left_count,
                    "intersection_frame_count": intersection,
                    "p_outcome_given_condition": intersection / left_count if left_count else np.nan,
                    "jaccard": intersection / union if union else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _select_unique_motion_events(events: pd.DataFrame, event_type: str, count: int) -> pd.DataFrame:
    subset = events.loc[events["event_type"] == event_type].copy()
    subset = subset.sort_values(
        ["max_severity", "duration_s", "motion_name", "start_frame"],
        ascending=[False, False, True, True],
    )
    selected = subset.drop_duplicates("motion_name", keep="first").head(count)
    if len(selected) < count:
        remainder = subset.loc[~subset.index.isin(selected.index)].head(count - len(selected))
        selected = pd.concat([selected, remainder])
    if len(selected) != count:
        raise ValueError(f"Could not select {count} cases for {event_type}")
    return selected


def _case_catalog(
    config: dict[str, Any], catalog: pd.DataFrame, frames: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    event_mapping = {
        "self_collision_nonhand": "SELF_COLLISION_NONHAND",
        "ground_penetration": "GROUND_PENETRATION",
        "joint_jump": "JOINT_JUMP",
    }
    metadata = catalog.set_index("motion_name")[["motion_category", "contact_policy", "pkl_path"]]
    fps = float(config["expected"]["fps"])
    padding = int(round(config["analysis"]["window_padding_s"] * fps))
    num_frames = frames.groupby("motion_name").size().to_dict()
    rows: list[dict[str, Any]] = []
    case_number = 0
    for case_type, count in config["analysis"]["case_counts"].items():
        selected = _select_unique_motion_events(events, event_mapping[case_type], int(count))
        for _, event in selected.iterrows():
            case_number += 1
            name = str(event["motion_name"])
            start = int(event["start_frame"])
            end = int(event["end_frame"])
            window_start = max(0, start - padding)
            window_end = min(int(num_frames[name]) - 1, end + padding)
            pose_frames = np.linspace(
                window_start,
                window_end,
                int(config["analysis"]["pose_frames_per_window"]),
            ).round().astype(int).tolist()
            rows.append(
                {
                    "case_id": f"C{case_number:02d}",
                    "case_type": case_type,
                    "motion_name": name,
                    "motion_category": metadata.loc[name, "motion_category"],
                    "contact_policy": metadata.loc[name, "contact_policy"],
                    "pkl_path": metadata.loc[name, "pkl_path"],
                    "event_start_frame": start,
                    "event_end_frame": end,
                    "event_duration_s": float(event["duration_s"]),
                    "entities": event["entities"],
                    "max_severity": float(event["max_severity"]),
                    "window_start_frame": window_start,
                    "window_end_frame": window_end,
                    "pose_frames": json.dumps(pose_frames, separators=(",", ":")),
                    "selection_rule": "maximum severity, then duration; distinct motion within type",
                }
            )
    for name in config["analysis"]["controls"]:
        case_number += 1
        nframes = int(num_frames[name])
        center = nframes // 2
        window_start = max(0, center - padding)
        window_end = min(nframes - 1, center + padding)
        pose_frames = np.linspace(
            window_start,
            window_end,
            int(config["analysis"]["pose_frames_per_window"]),
        ).round().astype(int).tolist()
        rows.append(
            {
                "case_id": f"C{case_number:02d}",
                "case_type": "control",
                "motion_name": name,
                "motion_category": metadata.loc[name, "motion_category"],
                "contact_policy": metadata.loc[name, "contact_policy"],
                "pkl_path": metadata.loc[name, "pkl_path"],
                "event_start_frame": center,
                "event_end_frame": center,
                "event_duration_s": 1.0 / fps,
                "entities": "[]",
                "max_severity": 0.0,
                "window_start_frame": window_start,
                "window_end_frame": window_end,
                "pose_frames": json.dumps(pose_frames, separators=(",", ":")),
                "selection_rule": "preregistered low-hard-failure control motion at sequence midpoint",
            }
        )
    return pd.DataFrame(rows)


def _load_qpos(path: Path) -> tuple[float, np.ndarray]:
    with path.open("rb") as stream:
        payload = pickle.load(stream)
    fps = float(payload["fps"])
    root_pos = np.asarray(payload["root_pos"], dtype=np.float64)
    root_xyzw = np.asarray(payload["root_rot"], dtype=np.float64)
    dof_pos = np.asarray(payload["dof_pos"], dtype=np.float64)
    root_wxyz = root_xyzw[:, [3, 0, 1, 2]]
    qpos = np.concatenate([root_pos, root_wxyz, dof_pos], axis=1)
    if qpos.ndim != 2 or qpos.shape[1] != 36 or not np.isfinite(qpos).all():
        raise ValueError(f"Invalid GMR trajectory: {path}")
    return fps, qpos


def _plot_case_timeline(case: pd.Series, frames: pd.DataFrame, path: Path) -> None:
    subset = frames.loc[
        (frames["motion_name"] == case["motion_name"])
        & frames["frame"].between(case["window_start_frame"], case["window_end_frame"])
    ].copy()
    time = subset["time_s"].to_numpy(float)
    fig, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(time, subset["max_joint_step_rad"], label="max joint step [rad]")
    axes[0].axhline(0.5, color="tab:red", linestyle="--", label="jump threshold")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].plot(time, subset["max_joint_vel_rad_s"], label="max joint velocity [rad/s]")
    axes[1].axhline(3 * np.pi, color="tab:red", linestyle="--", label="velocity threshold")
    axes[1].legend(loc="upper right", fontsize=8)
    axes[2].plot(time, subset["min_limit_margin_norm"], label="minimum normalized limit margin")
    axes[2].axhline(0.02, color="tab:red", linestyle="--", label="2% near-limit threshold")
    axes[2].legend(loc="upper right", fontsize=8)
    axes[3].plot(time, subset["penetration_depth_m"], label="ground penetration [m]")
    axes[3].fill_between(
        time,
        0,
        _as_bool(subset["self_collision_nonhand_flag"]).astype(float),
        alpha=0.25,
        label="non-hand self collision",
    )
    axes[3].legend(loc="upper right", fontsize=8)
    for axis in axes:
        axis.axvspan(
            float(case["event_start_frame"]) / 30.0,
            float(case["event_end_frame"]) / 30.0,
            color="tab:orange",
            alpha=0.2,
        )
        axis.grid(alpha=0.2)
    axes[-1].set_xlabel("time [s]")
    fig.suptitle(f"{case['case_id']} | {case['case_type']} | {case['motion_name']}")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_pose_montage(case: pd.Series, robot_xml: Path, path: Path) -> None:
    _, qpos = _load_qpos(Path(case["pkl_path"]))
    model = mujoco.MjModel.from_xml_path(str(robot_xml))
    data = mujoco.MjData(model)
    body_names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, index)
        for index in range(model.nbody)
    ]
    pelvis_id = body_names.index("pelvis")
    left_foot_id = body_names.index("left_ankle_roll_link")
    right_foot_id = body_names.index("right_ankle_roll_link")
    selected = _json_list(case["pose_frames"])
    figure = plt.figure(figsize=(3.2 * len(selected), 4.2))
    for plot_index, frame_index in enumerate(selected, start=1):
        data.qpos[:] = qpos[int(frame_index)]
        mujoco.mj_forward(model, data)
        positions = data.xpos.copy()
        positions[:, :2] -= positions[pelvis_id, :2]
        axis = figure.add_subplot(1, len(selected), plot_index, projection="3d")
        for body_id in range(1, model.nbody):
            parent = int(model.body_parentid[body_id])
            if parent <= 0:
                continue
            points = positions[[parent, body_id]]
            axis.plot(points[:, 0], points[:, 1], points[:, 2], color="0.25", linewidth=1.2)
        axis.scatter(positions[1:, 0], positions[1:, 1], positions[1:, 2], color="tab:blue", s=7)
        axis.scatter(
            positions[[left_foot_id, right_foot_id], 0],
            positions[[left_foot_id, right_foot_id], 1],
            positions[[left_foot_id, right_foot_id], 2],
            color="tab:red",
            s=18,
        )
        axis.plot([-0.8, 0.8], [-0.8, -0.8], [0, 0], alpha=0)
        axis.set_xlim(-0.8, 0.8)
        axis.set_ylim(-0.8, 0.8)
        axis.set_zlim(-0.25, 1.75)
        axis.view_init(elev=15, azim=-65)
        axis.set_title(f"frame {frame_index}", fontsize=8)
        axis.set_xticks([])
        axis.set_yticks([])
        axis.set_zticks([0.0, 1.0])
    figure.suptitle(f"{case['case_id']} | {case['case_type']} | {case['motion_name']} | static FK only")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_prevalence(strata: pd.DataFrame, metrics: list[str], path: Path) -> None:
    data = strata.loc[strata["scope"] != "all"].set_index("scope")
    values = data[[f"{metric}_pooled_frame_rate" for metric in metrics]].T
    values.index = metrics
    figure, axis = plt.subplots(figsize=(12, 7))
    values.plot(kind="bar", ax=axis)
    axis.set_ylabel("pooled flagged-frame rate")
    axis.set_xlabel("failure metric")
    axis.set_ylim(0, 1)
    axis.grid(axis="y", alpha=0.2)
    axis.legend(title="motion category", fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_overlap(overlap: pd.DataFrame, metrics: list[str], path: Path) -> None:
    pivot = overlap.pivot(index="condition", columns="outcome", values="p_outcome_given_condition")
    pivot = pivot.loc[metrics, metrics]
    figure, axis = plt.subplots(figsize=(9, 8))
    image = axis.imshow(pivot.to_numpy(), vmin=0, vmax=1, cmap="magma")
    axis.set_xticks(range(len(metrics)), metrics, rotation=35, ha="right")
    axis.set_yticks(range(len(metrics)), metrics)
    for row in range(len(metrics)):
        for column in range(len(metrics)):
            axis.text(column, row, f"{pivot.iloc[row, column]:.2f}", ha="center", va="center", fontsize=7)
    figure.colorbar(image, ax=axis, label="P(outcome | condition)")
    axis.set_title("Frame-level abnormality co-occurrence (descriptive)")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for name in ("mink", "mujoco", "numpy", "scipy", "pandas", "matplotlib", "PyYAML", "qpsolvers", "daqp"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _manifest(output: Path, config: dict[str, Any], audit: dict[str, Any]) -> Path:
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "run_manifest.json":
            files.append(
                {
                    "path": str(path.relative_to(output)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("cli.py"),
        Path(__file__).resolve().with_name("__init__.py"),
    ]
    manifest = {
        "schema_version": 1,
        "analysis_version": ANALYSIS_VERSION,
        "complete": True,
        "created_at": datetime.now().astimezone().isoformat(),
        "config": {
            "path": config["_config_path"],
            "sha256": sha256_file(config["_config_path"]),
        },
        "analysis_source_files": [
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in source_paths
        ],
        "input_audit_sha256": sha256_file(output / "input_audit.json"),
        "source_audit": audit,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": _package_versions(),
        },
        "files": files,
    }
    path = output / "run_manifest.json"
    _write_json(path, manifest)
    return path


def run_analysis(config_path: str | Path, output_dir: str | Path) -> AnalysisResult:
    config = load_config(config_path)
    output = Path(output_dir).expanduser().resolve()
    _prepare_output(output)
    tables = output / "tables"
    figures = output / "figures"
    cases_dir = output / "cases"
    tables.mkdir()
    figures.mkdir()
    cases_dir.mkdir()

    audit, catalog, original_summary, events = _audit_inputs(config)
    frames = _load_frame_metrics(config, catalog, original_summary)
    masks = _metric_masks(config, frames)
    metrics = list(masks)
    motions = _motion_summary(config, catalog, frames, masks)

    # Check the raw summary rates without copying score columns into any analysis table.
    specs = {spec["name"]: spec for spec in config["analysis"]["metrics"]}
    raw = original_summary.set_index("motion_name")
    recalculation_checks: dict[str, bool] = {}
    for metric in metrics:
        source_column = specs[metric].get("summary_rate")
        if source_column:
            actual = motions.set_index("motion_name")[f"{metric}_frame_rate"].sort_index()
            expected = raw[source_column].sort_index()
            recalculation_checks[metric] = bool(np.allclose(actual, expected, atol=1e-12, rtol=0))
    if not all(recalculation_checks.values()):
        raise ValueError(f"Recalculated frame rates differ from frozen summary: {recalculation_checks}")

    strata = _stratum_summary(motions, metrics)
    event_burden = _event_burden(events, catalog)
    joints = _joint_hotspots(frames)
    collisions = _collision_hotspots(events, Path(config["paths"]["robot_xml"]))
    penetration_bodies = _body_hotspots(frames, "penetration_bodies", "ground_penetration")
    undesired_bodies = _body_hotspots(
        frames, "undesired_ground_contact_bodies", "undesired_ground_contact"
    )
    body_hotspots = pd.concat([penetration_bodies, undesired_bodies], ignore_index=True)
    overlap = _overlap_table(masks)
    cases = _case_catalog(config, catalog, frames, events)

    audit["frame_rate_recalculation_checks"] = recalculation_checks
    audit["quality_score_column_loaded_with_frozen_summary"] = "quality_score" in original_summary.columns
    audit["quality_score_used_in_analysis"] = False
    _write_json(output / "input_audit.json", audit)
    motions.to_csv(tables / "motion_failure_summary.csv", index=False)
    strata.to_csv(tables / "stratum_failure_summary.csv", index=False)
    event_burden.to_csv(tables / "event_burden.csv", index=False)
    joints.to_csv(tables / "joint_hotspots.csv", index=False)
    collisions.to_csv(tables / "collision_pair_hotspots.csv", index=False)
    body_hotspots.to_csv(tables / "ground_contact_body_hotspots.csv", index=False)
    overlap.to_csv(tables / "abnormality_overlap.csv", index=False)
    cases.to_csv(tables / "failure_case_catalog.csv", index=False)

    _plot_prevalence(strata, metrics, figures / "failure_prevalence_by_category.png")
    _plot_overlap(overlap, metrics, figures / "abnormality_overlap_heatmap.png")
    for _, case in cases.iterrows():
        case_output = cases_dir / str(case["case_id"])
        case_output.mkdir()
        _plot_case_timeline(case, frames, case_output / "metric_timeline.png")
        _plot_pose_montage(
            case, Path(config["paths"]["robot_xml"]), case_output / "pose_montage.png"
        )
        _write_json(
            case_output / "case_metadata.json",
            {
                key: (value.item() if isinstance(value, np.generic) else value)
                for key, value in case.to_dict().items()
            },
        )

    all_scope = strata.loc[strata["scope"] == "all"].iloc[0]
    hard_fail_counts = {
        code: int(
            original_summary["failure_reason_codes"].map(lambda value: code in _json_list(value)).sum()
        )
        for code in ("SEVERE_PENETRATION", "SUSTAINED_SELF_COLLISION", "UNDESIRED_GROUND_CONTACT")
    }
    evidence = {
        "analysis_version": ANALYSIS_VERSION,
        "research_boundary": config["research_boundary"],
        "cohort": {
            "motion_count": int(len(motions)),
            "frame_count": int(motions["num_frames"].sum()),
            "stratum_counts": audit["stratum_counts"],
        },
        "frame_level": {
            metric: {
                "flagged_frame_count": int(all_scope[f"{metric}_frame_count"]),
                "pooled_frame_rate": float(all_scope[f"{metric}_pooled_frame_rate"]),
                "affected_motion_count": int(all_scope[f"{metric}_affected_motion_count"]),
                "median_motion_rate": float(all_scope[f"{metric}_motion_rate_median"]),
            }
            for metric in metrics
        },
        "hard_fail_affected_motion_counts": hard_fail_counts,
        "selected_case_count": int(len(cases)),
        "confirmed_code_facts": {
            "configuration_limit_enabled": True,
            "frozen_generation_velocity_limit_enabled": False,
            "collision_limit_present_in_gmr": False,
            "cross_frame_smoothing_objective_present_in_gmr": False,
            "per_frame_solver_allows_repeated_integrations": True,
        },
        "interpretation": {
            "joint_jump_given_velocity_violation_note": "Conditional relationships are descriptive, not causal.",
            "static_fk_proves_dynamic_feasibility": False,
            "quality_score_used": False,
        },
    }
    evidence_path = output / "evidence_summary.json"
    _write_json(evidence_path, evidence)
    manifest = _manifest(output, config, audit)
    return AnalysisResult(
        output_dir=output,
        manifest=manifest,
        evidence_summary=evidence_path,
        case_catalog=tables / "failure_case_catalog.csv",
    )


def verify_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    mismatches: list[str] = []
    for entry in payload["files"]:
        file_path = root / entry["path"]
        if not file_path.is_file():
            mismatches.append(f"missing:{entry['path']}")
            continue
        if file_path.stat().st_size != entry["size_bytes"]:
            mismatches.append(f"size:{entry['path']}")
        if sha256_file(file_path) != entry["sha256"]:
            mismatches.append(f"sha256:{entry['path']}")
    return {
        "ok": not mismatches and bool(payload.get("complete")),
        "checked_file_count": len(payload["files"]),
        "mismatches": mismatches,
    }


def finalize_visual_review(
    case_catalog: str | Path, review_yaml: str | Path, output_csv: str | Path
) -> Path:
    catalog_path = Path(case_catalog).expanduser().resolve()
    review_path = Path(review_yaml).expanduser().resolve()
    output_path = Path(output_csv).expanduser().resolve()
    if output_path.exists():
        raise ValueError(f"Review output already exists: {output_path}")
    catalog = pd.read_csv(catalog_path)
    with review_path.open(encoding="utf-8") as stream:
        review = yaml.safe_load(stream)
    records = review.get("reviews", [])
    if not isinstance(records, list):
        raise ValueError("reviews must be a list")
    review_table = pd.DataFrame(records)
    required = {"case_id", "visible_artifact", "metric_agreement", "notes"}
    if not required.issubset(review_table.columns):
        raise ValueError(f"Review is missing fields: {sorted(required - set(review_table.columns))}")
    if review_table["case_id"].duplicated().any():
        raise ValueError("Review case IDs must be unique")
    if set(review_table["case_id"]) != set(catalog["case_id"]):
        raise ValueError("Review case IDs do not exactly match the frozen catalog")
    allowed_artifact = {
        "confirmed",
        "partial",
        "likely_metric_artifact",
        "uncertain",
        "control_plausible",
    }
    allowed_agreement = {"agree", "partial", "disagree", "not_applicable"}
    if not set(review_table["visible_artifact"]).issubset(allowed_artifact):
        raise ValueError("Review contains an invalid visible_artifact value")
    if not set(review_table["metric_agreement"]).issubset(allowed_agreement):
        raise ValueError("Review contains an invalid metric_agreement value")
    if review_table["notes"].astype(str).str.len().lt(40).any():
        raise ValueError("Every review note must contain concrete evidence")
    review_table["reviewer"] = review["reviewer"]
    review_table["reviewed_at"] = review["reviewed_at"]
    merged = catalog.merge(review_table, on="case_id", how="left", validate="one_to_one")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False)
    return output_path
