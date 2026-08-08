"""A2 Collision-GMR layered on the frozen Temporal-GMR v2 implementation."""

from __future__ import annotations

import csv
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

import mink
import mujoco
import numpy as np

from .collision_model import DEFAULT_HAND_PATTERNS, body_tree_distance
from .temporal import TemporalGMRConfig, TemporalGeneralMotionRetargeting


@dataclass(frozen=True)
class CollisionGMRConfig:
    """Frozen A2 collision-limit parameters."""

    minimum_distance_m: float = 0.005
    detection_distance_m: float = 0.020
    gain: float = 0.85
    bound_relaxation: float = 0.0
    broadphase: bool = True
    expected_pair_count: int = 362
    minimum_tree_distance: int = 3
    hand_patterns: tuple[str, ...] = DEFAULT_HAND_PATTERNS
    enabled: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(self.minimum_distance_m) or self.minimum_distance_m < 0.0:
            raise ValueError("minimum_distance_m must be finite and >= 0")
        if (
            not np.isfinite(self.detection_distance_m)
            or self.detection_distance_m <= self.minimum_distance_m
        ):
            raise ValueError("detection_distance_m must exceed minimum_distance_m")
        if not np.isfinite(self.gain) or not 0.0 < self.gain <= 1.0:
            raise ValueError("gain must be in (0, 1]")
        if self.bound_relaxation != 0.0:
            raise ValueError("I1 preregistration requires bound_relaxation=0")
        if self.expected_pair_count < 1:
            raise ValueError("expected_pair_count must be positive")
        if self.minimum_tree_distance < 3:
            raise ValueError("I1 preregistration requires minimum_tree_distance>=3")
        if not self.hand_patterns:
            raise ValueError("hand_patterns must not be empty")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CollisionFrameDiagnostic:
    frame_index: int
    audited_pair_count: int
    broadphase_candidate_count: int
    active_pair_count: int
    below_minimum_pair_count: int
    penetrating_pair_count: int
    minimum_pair_distance_m: float
    closest_geom_a: str | None
    closest_geom_b: str | None
    closest_body_a: str | None
    closest_body_b: str | None


class DeterministicCollisionAvoidanceLimit(mink.CollisionAvoidanceLimit):
    """Sort Mink's deduplicated pairs so QP row order is reproducible."""

    def _construct_geom_id_pairs(self, geom_pairs):  # type: ignore[override]
        return sorted(super()._construct_geom_id_pairs(geom_pairs))


_MODEL_OVERRIDE_LOCK = threading.RLock()


@contextmanager
def _temporary_robot_xml(robot: str, derived_xml: Path) -> Iterator[None]:
    """Redirect only the synchronous upstream constructor, restoring on failure."""
    import general_motion_retargeting.motion_retarget as upstream

    with _MODEL_OVERRIDE_LOCK:
        if robot not in upstream.ROBOT_XML_DICT:
            raise KeyError(f"Unknown upstream robot: {robot}")
        original = upstream.ROBOT_XML_DICT[robot]
        upstream.ROBOT_XML_DICT[robot] = derived_xml
        try:
            yield
        finally:
            upstream.ROBOT_XML_DICT[robot] = original


def load_audited_geom_pairs(
    path: str | Path,
    model: mujoco.MjModel,
    config: CollisionGMRConfig,
) -> tuple[tuple[int, int], ...]:
    pair_path = Path(path).expanduser().resolve()
    with pair_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "geom_a_id",
        "geom_a_name",
        "body_a_id",
        "body_a_name",
        "geom_b_id",
        "geom_b_name",
        "body_b_id",
        "body_b_name",
        "tree_distance",
    }
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Collision pair CSV is empty or missing columns: {required}")
    pairs: list[tuple[int, int]] = []
    for index, row in enumerate(rows):
        geom_a = int(row["geom_a_id"])
        geom_b = int(row["geom_b_id"])
        if not 0 <= geom_a < geom_b < model.ngeom:
            raise ValueError(f"Invalid ordered geom IDs at row {index}: {(geom_a, geom_b)}")
        for geom_id, geom_column, body_id_column, body_column in (
            (geom_a, "geom_a_name", "body_a_id", "body_a_name"),
            (geom_b, "geom_b_name", "body_b_id", "body_b_name"),
        ):
            actual_geom = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
            actual_body_id = int(model.geom_bodyid[geom_id])
            actual_body = mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, actual_body_id
            )
            if actual_geom != row[geom_column]:
                raise ValueError(f"Geom name mismatch at pair row {index}")
            if actual_body_id != int(row[body_id_column]) or actual_body != row[body_column]:
                raise ValueError(f"Geom body mismatch at pair row {index}")
            if any(pattern in actual_body for pattern in config.hand_patterns):
                raise ValueError(f"Allowed hand body leaked into pair row {index}: {actual_body}")
        body_a = int(model.geom_bodyid[geom_a])
        body_b = int(model.geom_bodyid[geom_b])
        distance = body_tree_distance(model, body_a, body_b)
        if distance != int(row["tree_distance"]) or distance < config.minimum_tree_distance:
            raise ValueError(f"Body-tree distance mismatch at pair row {index}")
        pairs.append((geom_a, geom_b))
    if len(pairs) != config.expected_pair_count:
        raise ValueError(
            f"Expected {config.expected_pair_count} audited pairs, got {len(pairs)}"
        )
    if len(pairs) != len(set(pairs)):
        raise ValueError("Collision pair CSV contains duplicates")
    return tuple(pairs)


class CollisionGeneralMotionRetargeting(TemporalGeneralMotionRetargeting):
    """Temporal-GMR v2 plus an audited non-neighbour collision velocity limit."""

    def __init__(
        self,
        *args: Any,
        temporal_config: TemporalGMRConfig,
        collision_config: CollisionGMRConfig,
        derived_robot_xml: str | Path,
        collision_pairs_csv: str | Path,
        **kwargs: Any,
    ) -> None:
        if not collision_config.enabled:
            raise ValueError("Use TemporalGeneralMotionRetargeting when collision is disabled")
        robot = kwargs.get("tgt_robot")
        if robot is None and len(args) >= 2:
            robot = args[1]
        if not isinstance(robot, str):
            raise ValueError("tgt_robot must be provided for Collision-GMR")
        derived = Path(derived_robot_xml).expanduser().resolve()
        pair_csv = Path(collision_pairs_csv).expanduser().resolve()
        if not derived.is_file() or not pair_csv.is_file():
            raise FileNotFoundError(derived if not derived.is_file() else pair_csv)
        with _temporary_robot_xml(robot, derived):
            super().__init__(*args, temporal_config=temporal_config, **kwargs)
        if Path(self.xml_file).resolve() != derived:
            raise RuntimeError("Upstream constructor did not load the derived collision model")
        self.collision_config = collision_config
        self.derived_robot_xml = derived
        self.collision_pairs_csv = pair_csv
        self.audited_geom_id_pairs = load_audited_geom_pairs(
            pair_csv, self.model, collision_config
        )
        geom_pairs = [((geom_a,), (geom_b,)) for geom_a, geom_b in self.audited_geom_id_pairs]
        self.collision_limit = DeterministicCollisionAvoidanceLimit(
            self.model,
            geom_pairs=geom_pairs,
            gain=collision_config.gain,
            minimum_distance_from_collisions=collision_config.minimum_distance_m,
            collision_detection_distance=collision_config.detection_distance_m,
            bound_relaxation=collision_config.bound_relaxation,
            broadphase=collision_config.broadphase,
        )
        if tuple(self.collision_limit.geom_id_pairs) != self.audited_geom_id_pairs:
            raise RuntimeError("Runtime Mink pair order differs from the audited pair CSV")
        self.ik_limits.append(self.collision_limit)
        self.collision_frame_diagnostics: list[CollisionFrameDiagnostic] = []

    def _collision_state(self) -> CollisionFrameDiagnostic:
        pairs = np.asarray(self.audited_geom_id_pairs, dtype=np.int64)
        geom_a = pairs[:, 0]
        geom_b = pairs[:, 1]
        center_delta = self.configuration.data.geom_xpos[geom_a] - self.configuration.data.geom_xpos[geom_b]
        center_distance_sq = np.einsum("ij,ij->i", center_delta, center_delta)
        bound = (
            self.model.geom_rbound[geom_a]
            + self.model.geom_rbound[geom_b]
            + self.collision_config.detection_distance_m
        )
        candidate_indices = np.flatnonzero(center_distance_sq <= bound * bound)
        active = below = penetrating = 0
        minimum = self.collision_config.detection_distance_m
        closest: tuple[int, int] | None = None
        fromto = np.empty(6, dtype=np.float64)
        for pair_index in candidate_indices:
            first, second = self.audited_geom_id_pairs[int(pair_index)]
            distance = float(
                mujoco.mj_geomDistance(
                    self.model,
                    self.configuration.data,
                    first,
                    second,
                    self.collision_config.detection_distance_m,
                    fromto,
                )
            )
            if distance < self.collision_config.detection_distance_m - 1e-12:
                active += 1
            if distance < self.collision_config.minimum_distance_m:
                below += 1
            if distance < 0.0:
                penetrating += 1
            if distance < minimum:
                minimum = distance
                closest = (first, second)
        if closest is None:
            names: tuple[str | None, str | None, str | None, str | None] = (
                None, None, None, None
            )
        else:
            first, second = closest
            body_a = int(self.model.geom_bodyid[first])
            body_b = int(self.model.geom_bodyid[second])
            names = (
                mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, first),
                mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, second),
                mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_a),
                mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_b),
            )
        return CollisionFrameDiagnostic(
            frame_index=len(self.collision_frame_diagnostics),
            audited_pair_count=len(self.audited_geom_id_pairs),
            broadphase_candidate_count=len(candidate_indices),
            active_pair_count=active,
            below_minimum_pair_count=below,
            penetrating_pair_count=penetrating,
            minimum_pair_distance_m=float(minimum),
            closest_geom_a=names[0],
            closest_geom_b=names[1],
            closest_body_a=names[2],
            closest_body_b=names[3],
        )

    def retarget(self, human_data: Any, offset_to_ground: bool = False) -> np.ndarray:
        output = super().retarget(human_data, offset_to_ground)
        diagnostic = self._collision_state()
        if diagnostic.frame_index != len(self.frame_diagnostics) - 1:
            raise RuntimeError("Temporal and collision diagnostics lost frame alignment")
        self.collision_frame_diagnostics.append(diagnostic)
        return output
