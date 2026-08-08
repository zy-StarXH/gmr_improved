"""A3 Contact-GMR layered on the frozen Collision-GMR v1 implementation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import mink
import mujoco
import numpy as np

from .collision import CollisionGeneralMotionRetargeting


@dataclass(frozen=True)
class ContactGMRConfig:
    """Preregistered contact inference, foot-anchor and root-lift parameters."""

    human_left_foot_name: str = "LeftFootMod"
    human_right_foot_name: str = "RightFootMod"
    ground_percentile: float = 2.0
    enter_height_m: float = 0.04
    exit_height_m: float = 0.06
    enter_vertical_speed_m_s: float = 0.20
    exit_vertical_speed_m_s: float = 0.40
    enter_horizontal_speed_m_s: float = 0.20
    exit_horizontal_speed_m_s: float = 0.40
    left_foot_body: str = "left_ankle_roll_link"
    right_foot_body: str = "right_ankle_roll_link"
    anchor_xy_cost: float = 100.0
    anchor_z_cost: float = 50.0
    sole_clearance_m: float = 0.002
    target_max_ground_penetration_m: float = 0.005
    max_root_lift_m: float = 0.050
    max_root_lift_rise_per_frame_m: float = 0.020
    max_root_lift_release_per_frame_m: float = 0.005
    sole_sphere_max_radius_m: float = 0.010
    expected_sole_geom_count_per_foot: int = 4
    enable_feet_only_anchors: bool = True
    enable_feet_only_root_lift: bool = True
    enable_floor_motion_anchors: bool = False
    enable_floor_motion_root_lift: bool = False
    enabled: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.ground_percentile <= 10.0:
            raise ValueError("ground_percentile must be in [0, 10]")
        positive = {
            "enter_height_m": self.enter_height_m,
            "exit_height_m": self.exit_height_m,
            "enter_vertical_speed_m_s": self.enter_vertical_speed_m_s,
            "exit_vertical_speed_m_s": self.exit_vertical_speed_m_s,
            "enter_horizontal_speed_m_s": self.enter_horizontal_speed_m_s,
            "exit_horizontal_speed_m_s": self.exit_horizontal_speed_m_s,
            "anchor_xy_cost": self.anchor_xy_cost,
            "anchor_z_cost": self.anchor_z_cost,
            "sole_clearance_m": self.sole_clearance_m,
            "target_max_ground_penetration_m": self.target_max_ground_penetration_m,
            "max_root_lift_m": self.max_root_lift_m,
            "max_root_lift_rise_per_frame_m": self.max_root_lift_rise_per_frame_m,
            "max_root_lift_release_per_frame_m": self.max_root_lift_release_per_frame_m,
            "sole_sphere_max_radius_m": self.sole_sphere_max_radius_m,
        }
        for name, value in positive.items():
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
        if self.exit_height_m <= self.enter_height_m:
            raise ValueError("exit_height_m must exceed enter_height_m")
        if self.exit_vertical_speed_m_s <= self.enter_vertical_speed_m_s:
            raise ValueError("exit_vertical_speed_m_s must exceed enter threshold")
        if self.exit_horizontal_speed_m_s <= self.enter_horizontal_speed_m_s:
            raise ValueError("exit_horizontal_speed_m_s must exceed enter threshold")
        if self.target_max_ground_penetration_m >= self.max_root_lift_m:
            raise ValueError("target penetration must be smaller than maximum root lift")
        if self.expected_sole_geom_count_per_foot < 1:
            raise ValueError("expected sole geom count must be positive")
        if self.enable_floor_motion_anchors or self.enable_floor_motion_root_lift:
            raise ValueError("I2 v1 preregistration requires floor_motion semantic no-op")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanContactFrame:
    frame_index: int
    left_contact: bool
    right_contact: bool
    left_transition: str
    right_transition: str
    left_height_above_ground_m: float
    right_height_above_ground_m: float
    left_vertical_speed_m_s: float
    right_vertical_speed_m_s: float
    left_horizontal_speed_m_s: float
    right_horizontal_speed_m_s: float


@dataclass(frozen=True)
class HumanContactSequence:
    policy: str
    fps: float
    ground_height_m: float
    frames: tuple[HumanContactFrame, ...]


@dataclass(frozen=True)
class ContactFrameDiagnostic:
    frame_index: int
    contact_policy: str
    left_human_contact: bool
    right_human_contact: bool
    left_transition: str
    right_transition: str
    active_anchor_count: int
    left_anchor_error_m: float | None
    right_anchor_error_m: float | None
    pre_left_sole_height_m: float
    pre_right_sole_height_m: float
    post_left_sole_height_m: float
    post_right_sole_height_m: float
    pre_max_ground_penetration_m: float
    requested_root_lift_m: float
    applied_root_lift_m: float
    root_lift_clipped: bool
    post_max_ground_penetration_m: float
    root_z_before_m: float
    root_z_after_m: float


def _transition(previous: bool, current: bool) -> str:
    if not previous and current:
        return "enter"
    if previous and not current:
        return "exit"
    return "stay_contact" if current else "stay_swing"


def _infer_one_foot(
    heights: np.ndarray,
    vertical_speed: np.ndarray,
    horizontal_speed: np.ndarray,
    config: ContactGMRConfig,
) -> tuple[np.ndarray, tuple[str, ...]]:
    count = len(heights)
    states = np.zeros(count, dtype=bool)
    transitions: list[str] = []
    previous = False
    for index in range(count):
        if previous:
            current = not (
                heights[index] > config.exit_height_m
                or abs(vertical_speed[index]) > config.exit_vertical_speed_m_s
                or horizontal_speed[index] > config.exit_horizontal_speed_m_s
            )
        else:
            current = bool(
                heights[index] <= config.enter_height_m
                and abs(vertical_speed[index]) <= config.enter_vertical_speed_m_s
                and horizontal_speed[index] <= config.enter_horizontal_speed_m_s
            )
        states[index] = current
        transitions.append(_transition(previous, current))
        previous = current
    return states, tuple(transitions)


def infer_human_contact_sequence(
    human_frames: Sequence[dict[str, Any]],
    fps: float,
    contact_policy: str,
    config: ContactGMRConfig,
) -> HumanContactSequence:
    """Infer causal per-foot contacts from source height/velocity with hysteresis."""

    if not human_frames:
        raise ValueError("human_frames must not be empty")
    if not np.isfinite(fps) or fps <= 0.0:
        raise ValueError("fps must be finite and > 0")
    if contact_policy not in {"feet_only", "floor_motion"}:
        raise ValueError(f"Unsupported contact policy: {contact_policy}")
    names = (config.human_left_foot_name, config.human_right_foot_name)
    positions = np.empty((len(human_frames), 2, 3), dtype=np.float64)
    for frame_index, frame in enumerate(human_frames):
        for side, name in enumerate(names):
            if name not in frame:
                raise ValueError(f"Human frame {frame_index} is missing {name}")
            position = np.asarray(frame[name][0], dtype=np.float64)
            if position.shape != (3,) or not np.isfinite(position).all():
                raise ValueError(f"Invalid {name} position at frame {frame_index}")
            positions[frame_index, side] = position
    ground = float(np.percentile(positions[:, :, 2], config.ground_percentile))
    heights = positions[:, :, 2] - ground
    velocity = np.zeros_like(positions)
    velocity[1:] = np.diff(positions, axis=0) * fps
    vertical = velocity[:, :, 2]
    horizontal = np.linalg.norm(velocity[:, :, :2], axis=2)

    if contact_policy == "floor_motion":
        states = np.zeros((len(human_frames), 2), dtype=bool)
        transitions = (
            tuple("stay_swing" for _ in human_frames),
            tuple("stay_swing" for _ in human_frames),
        )
    else:
        left = _infer_one_foot(heights[:, 0], vertical[:, 0], horizontal[:, 0], config)
        right = _infer_one_foot(heights[:, 1], vertical[:, 1], horizontal[:, 1], config)
        states = np.column_stack([left[0], right[0]])
        transitions = (left[1], right[1])
    frames = tuple(
        HumanContactFrame(
            frame_index=index,
            left_contact=bool(states[index, 0]),
            right_contact=bool(states[index, 1]),
            left_transition=transitions[0][index],
            right_transition=transitions[1][index],
            left_height_above_ground_m=float(heights[index, 0]),
            right_height_above_ground_m=float(heights[index, 1]),
            left_vertical_speed_m_s=float(vertical[index, 0]),
            right_vertical_speed_m_s=float(vertical[index, 1]),
            left_horizontal_speed_m_s=float(horizontal[index, 0]),
            right_horizontal_speed_m_s=float(horizontal[index, 1]),
        )
        for index in range(len(human_frames))
    )
    return HumanContactSequence(
        policy=contact_policy,
        fps=float(fps),
        ground_height_m=ground,
        frames=frames,
    )


class ContactGeneralMotionRetargeting(CollisionGeneralMotionRetargeting):
    """Collision-GMR plus source-contact foot anchors and bounded root lift."""

    def __init__(
        self,
        *args: Any,
        contact_config: ContactGMRConfig,
        contact_policy: str,
        **kwargs: Any,
    ) -> None:
        if not contact_config.enabled:
            raise ValueError("Use CollisionGeneralMotionRetargeting when contact is disabled")
        if contact_policy not in {"feet_only", "floor_motion"}:
            raise ValueError(f"Unsupported contact policy: {contact_policy}")
        super().__init__(*args, **kwargs)
        self.contact_config = contact_config
        self.contact_policy = contact_policy
        self.floor_geom_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor"
        )
        if self.floor_geom_id < 0:
            raise ValueError("Derived robot model has no floor geom")
        self.foot_body_ids = {
            "left": self._require_body(contact_config.left_foot_body),
            "right": self._require_body(contact_config.right_foot_body),
        }
        self.sole_geom_ids = {
            side: self._find_sole_geoms(body_id)
            for side, body_id in self.foot_body_ids.items()
        }
        self.anchor_tasks = {
            side: mink.FrameTask(
                frame_name=(
                    contact_config.left_foot_body
                    if side == "left"
                    else contact_config.right_foot_body
                ),
                frame_type="body",
                position_cost=np.array(
                    [
                        contact_config.anchor_xy_cost,
                        contact_config.anchor_xy_cost,
                        contact_config.anchor_z_cost,
                    ]
                ),
                orientation_cost=0.0,
                lm_damping=1.0,
            )
            for side in ("left", "right")
        }
        self.anchor_positions: dict[str, np.ndarray | None] = {
            "left": None,
            "right": None,
        }
        self._active_anchor_tasks: tuple[mink.FrameTask, ...] = ()
        self.previous_applied_root_lift_m = 0.0
        self.contact_frame_diagnostics: list[ContactFrameDiagnostic] = []

    def _require_body(self, name: str) -> int:
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body_id < 0:
            raise ValueError(f"Robot foot body does not exist: {name}")
        return int(body_id)

    def _find_sole_geoms(self, body_id: int) -> tuple[int, ...]:
        ids = tuple(
            geom_id
            for geom_id in range(self.model.ngeom)
            if int(self.model.geom_bodyid[geom_id]) == body_id
            and int(self.model.geom_type[geom_id])
            == int(mujoco.mjtGeom.mjGEOM_SPHERE)
            and float(self.model.geom_size[geom_id, 0])
            <= self.contact_config.sole_sphere_max_radius_m
        )
        if len(ids) != self.contact_config.expected_sole_geom_count_per_foot:
            raise ValueError(
                f"Expected {self.contact_config.expected_sole_geom_count_per_foot} "
                f"sole spheres for body {body_id}, got {len(ids)}"
            )
        return ids

    def _sole_height(self, side: str) -> float:
        ids = self.sole_geom_ids[side]
        return float(
            min(
                self.configuration.data.geom_xpos[geom_id, 2]
                - self.model.geom_size[geom_id, 0]
                for geom_id in ids
            )
        )

    def _set_anchor(self, side: str) -> None:
        body_id = self.foot_body_ids[side]
        position = np.array(self.configuration.data.xpos[body_id], copy=True)
        position[2] += self.contact_config.sole_clearance_m - self._sole_height(side)
        rotation = np.array(self.configuration.data.xquat[body_id], copy=True)
        self.anchor_positions[side] = position
        self.anchor_tasks[side].set_target(
            mink.SE3.from_rotation_and_translation(mink.SO3(rotation), position)
        )

    def _prepare_anchors(self, contact: HumanContactFrame) -> None:
        if self.contact_policy != "feet_only" or not self.contact_config.enable_feet_only_anchors:
            self.anchor_positions = {"left": None, "right": None}
            self._active_anchor_tasks = ()
            return
        if self.previous_output_qpos is None:
            # The model starts in its neutral pose, which is generally in a
            # different world location from the first BVH frame. Establishing
            # an anchor before the first retarget would freeze that fictitious
            # neutral-world position. The first aligned output seeds anchors.
            self.anchor_positions = {"left": None, "right": None}
            self._active_anchor_tasks = ()
            return
        active: list[mink.FrameTask] = []
        for side, state, transition in (
            ("left", contact.left_contact, contact.left_transition),
            ("right", contact.right_contact, contact.right_transition),
        ):
            if state:
                if transition == "enter" or self.anchor_positions[side] is None:
                    self._set_anchor(side)
                active.append(self.anchor_tasks[side])
            else:
                self.anchor_positions[side] = None
        self._active_anchor_tasks = tuple(active)

    def _solve_stage(self, base_tasks: list[Any], error_fn: Any) -> tuple[int, float, float]:
        # Keep the frozen Temporal-GMR solve order; only insert active anchors.
        tasks = [
            *base_tasks,
            *self._active_anchor_tasks,
            self.previous_posture_task,
            self.soft_limit_task,
        ]
        limits = [*self.ik_limits, self.frame_velocity_limit]
        current_error = float(error_fn())
        error_before = current_error
        dt = float(self.configuration.model.opt.timestep)
        velocity = mink.solve_ik(
            self.configuration,
            tasks,
            dt,
            self.solver,
            damping=self.damping,
            limits=limits,
        )
        self.configuration.integrate_inplace(velocity, dt)
        solve_count = 1
        next_error = float(error_fn())
        num_iter = 0
        while current_error - next_error > 0.001 and num_iter < self.max_iter:
            current_error = next_error
            velocity = mink.solve_ik(
                self.configuration,
                tasks,
                dt,
                self.solver,
                damping=self.damping,
                limits=limits,
            )
            self.configuration.integrate_inplace(velocity, dt)
            solve_count += 1
            next_error = float(error_fn())
            num_iter += 1
        return solve_count, error_before, next_error

    def _max_ground_penetration(self) -> float:
        maximum = 0.0
        for contact in self.configuration.data.contact[: self.configuration.data.ncon]:
            if self.floor_geom_id in (int(contact.geom1), int(contact.geom2)):
                maximum = max(maximum, max(0.0, -float(contact.dist)))
        return maximum

    def _root_lift(self, pre_depth: float) -> tuple[float, float, bool]:
        if self.contact_policy != "feet_only" or not self.contact_config.enable_feet_only_root_lift:
            self.previous_applied_root_lift_m = 0.0
            return 0.0, 0.0, False
        requested = max(
            0.0,
            pre_depth - self.contact_config.target_max_ground_penetration_m,
        )
        capped = min(requested, self.contact_config.max_root_lift_m)
        previous = self.previous_applied_root_lift_m
        if capped > previous:
            applied = min(
                capped,
                previous + self.contact_config.max_root_lift_rise_per_frame_m,
            )
        else:
            applied = max(
                capped,
                previous - self.contact_config.max_root_lift_release_per_frame_m,
            )
        self.previous_applied_root_lift_m = float(applied)
        clipped = not np.isclose(applied, requested, atol=1e-12, rtol=0.0)
        return float(requested), float(applied), bool(clipped)

    def _anchor_error(self, side: str) -> float | None:
        target = self.anchor_positions[side]
        if target is None:
            return None
        current = self.configuration.data.xpos[self.foot_body_ids[side]]
        return float(np.linalg.norm(current - target))

    def retarget(
        self,
        human_data: Any,
        contact_frame: HumanContactFrame,
        offset_to_ground: bool = False,
    ) -> np.ndarray:
        if contact_frame.frame_index != len(self.contact_frame_diagnostics):
            raise ValueError("Human contact frame is out of sequence")
        self._prepare_anchors(contact_frame)
        output = super().retarget(human_data, offset_to_ground)
        mujoco.mj_forward(self.model, self.configuration.data)
        pre_left = self._sole_height("left")
        pre_right = self._sole_height("right")
        pre_depth = self._max_ground_penetration()
        requested, applied, clipped = self._root_lift(pre_depth)
        root_before = float(output[2])
        if applied > 0.0:
            output = output.copy()
            output[2] += applied
            self.configuration.update(output)
            mujoco.mj_forward(self.model, self.configuration.data)
            self.previous_output_qpos = output.copy()
        if (
            self.contact_policy == "feet_only"
            and self.contact_config.enable_feet_only_anchors
        ):
            for side, state in (
                ("left", contact_frame.left_contact),
                ("right", contact_frame.right_contact),
            ):
                if state and self.anchor_positions[side] is None:
                    self._set_anchor(side)
        post_depth = self._max_ground_penetration()
        diagnostic = ContactFrameDiagnostic(
            frame_index=contact_frame.frame_index,
            contact_policy=self.contact_policy,
            left_human_contact=contact_frame.left_contact,
            right_human_contact=contact_frame.right_contact,
            left_transition=contact_frame.left_transition,
            right_transition=contact_frame.right_transition,
            active_anchor_count=len(self._active_anchor_tasks),
            left_anchor_error_m=self._anchor_error("left"),
            right_anchor_error_m=self._anchor_error("right"),
            pre_left_sole_height_m=pre_left,
            pre_right_sole_height_m=pre_right,
            post_left_sole_height_m=self._sole_height("left"),
            post_right_sole_height_m=self._sole_height("right"),
            pre_max_ground_penetration_m=pre_depth,
            requested_root_lift_m=requested,
            applied_root_lift_m=applied,
            root_lift_clipped=clipped,
            post_max_ground_penetration_m=post_depth,
            root_z_before_m=root_before,
            root_z_after_m=float(output[2]),
        )
        self.contact_frame_diagnostics.append(diagnostic)
        return output
