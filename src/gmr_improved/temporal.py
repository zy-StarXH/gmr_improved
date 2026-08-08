"""Temporal extensions for GMR without modifying the upstream repository.

The key distinction from :class:`mink.VelocityLimit` is that
``WholeFrameVelocityLimit`` owns a reference configuration and a 30 Hz frame
budget.  Every internal IK solve sees the *remaining* part of that same budget,
so two task stages and repeated local iterations cannot each spend it again.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import mink
import mujoco
import numpy as np
from mink.limits import Constraint, Limit
from mink.tasks import Task

from general_motion_retargeting import GeneralMotionRetargeting


@dataclass(frozen=True)
class TemporalGMRConfig:
    """Configuration of the A1 Temporal-GMR intervention."""

    output_fps: float = 30.0
    max_joint_velocity_rad_s: float = float(3.0 * np.pi)
    previous_posture_cost: float = 1.0
    soft_limit_cost: float = 10.0
    soft_limit_margin_fraction: float = 0.03
    soft_limit_min_margin_rad: float = 0.0
    trust_region_tolerance_rad: float = 1e-7
    enabled: bool = True

    def __post_init__(self) -> None:
        finite_positive = {
            "output_fps": self.output_fps,
            "max_joint_velocity_rad_s": self.max_joint_velocity_rad_s,
        }
        for name, value in finite_positive.items():
            if not np.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0")
        nonnegative = {
            "previous_posture_cost": self.previous_posture_cost,
            "soft_limit_cost": self.soft_limit_cost,
            "soft_limit_min_margin_rad": self.soft_limit_min_margin_rad,
            "trust_region_tolerance_rad": self.trust_region_tolerance_rad,
        }
        for name, value in nonnegative.items():
            if not np.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and >= 0")
        if (
            not np.isfinite(self.soft_limit_margin_fraction)
            or not 0.0 <= self.soft_limit_margin_fraction < 0.5
        ):
            raise ValueError("soft_limit_margin_fraction must be in [0, 0.5)")

    @property
    def frame_dt(self) -> float:
        return 1.0 / self.output_fps

    @property
    def max_joint_step_rad(self) -> float:
        return self.max_joint_velocity_rad_s * self.frame_dt

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ScalarJointMetadata:
    names: tuple[str, ...]
    qpos_indices: np.ndarray
    dof_indices: np.ndarray
    lower: np.ndarray
    upper: np.ndarray


def _limited_scalar_joints(model: mujoco.MjModel) -> _ScalarJointMetadata:
    names: list[str] = []
    qpos_indices: list[int] = []
    dof_indices: list[int] = []
    lower: list[float] = []
    upper: list[float] = []
    for joint_id in range(model.njnt):
        joint_type = int(model.jnt_type[joint_id])
        if joint_type == int(mujoco.mjtJoint.mjJNT_FREE) or not model.jnt_limited[joint_id]:
            continue
        if joint_type not in {
            int(mujoco.mjtJoint.mjJNT_HINGE),
            int(mujoco.mjtJoint.mjJNT_SLIDE),
        }:
            raise ValueError(
                "Temporal-GMR currently supports limited scalar hinge/slide joints; "
                f"joint id {joint_id} has type {joint_type}"
            )
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint_id)
        if name is None:
            raise ValueError(f"Limited joint id {joint_id} has no name")
        names.append(name)
        qpos_indices.append(int(model.jnt_qposadr[joint_id]))
        dof_indices.append(int(model.jnt_dofadr[joint_id]))
        lower.append(float(model.jnt_range[joint_id, 0]))
        upper.append(float(model.jnt_range[joint_id, 1]))
    if not names:
        raise ValueError("Robot model contains no limited scalar joints")
    return _ScalarJointMetadata(
        names=tuple(names),
        qpos_indices=np.asarray(qpos_indices, dtype=np.int64),
        dof_indices=np.asarray(dof_indices, dtype=np.int64),
        lower=np.asarray(lower, dtype=np.float64),
        upper=np.asarray(upper, dtype=np.float64),
    )


class WholeFrameVelocityLimit(Limit):
    """Bound cumulative joint displacement relative to the previous output frame.

    Mink optimizes a tangent displacement ``delta_q`` on every internal solve.
    If ``d`` is the displacement already spent since ``reference_qpos``, this
    limit applies ``-budget <= d + delta_q <= budget``.  The internal solver
    timestep is intentionally ignored: the budget belongs to the output frame.
    Floating-base coordinates are not constrained, matching the joint-velocity
    metric and Mink's standard ``VelocityLimit`` scope.
    """

    def __init__(
        self,
        model: mujoco.MjModel,
        max_velocity: float | np.ndarray,
        frame_dt: float,
    ) -> None:
        self.model = model
        self.joints = _limited_scalar_joints(model)
        velocity = np.broadcast_to(
            np.asarray(max_velocity, dtype=np.float64), self.joints.dof_indices.shape
        ).copy()
        if not np.isfinite(velocity).all() or np.any(velocity <= 0.0):
            raise ValueError("max_velocity must contain finite positive values")
        if not np.isfinite(frame_dt) or frame_dt <= 0.0:
            raise ValueError("frame_dt must be finite and > 0")
        self.max_velocity = velocity
        self.frame_dt = float(frame_dt)
        self.budget = velocity * self.frame_dt
        self.projection_matrix = np.eye(model.nv)[self.joints.dof_indices]
        self.reference_qpos: np.ndarray | None = None

    def set_reference(self, qpos: np.ndarray | None) -> None:
        if qpos is None:
            self.reference_qpos = None
            return
        reference = np.asarray(qpos, dtype=np.float64)
        if reference.shape != (self.model.nq,):
            raise ValueError(
                f"reference_qpos must have shape ({self.model.nq},), got {reference.shape}"
            )
        if not np.isfinite(reference).all():
            raise ValueError("reference_qpos contains NaN or Inf")
        self.reference_qpos = reference.copy()

    def displacement_from_reference(self, qpos: np.ndarray) -> np.ndarray:
        if self.reference_qpos is None:
            raise RuntimeError("Whole-frame reference is not set")
        current = np.asarray(qpos, dtype=np.float64)
        tangent = np.empty(self.model.nv, dtype=np.float64)
        mujoco.mj_differentiatePos(
            m=self.model,
            qvel=tangent,
            dt=1.0,
            qpos1=self.reference_qpos,
            qpos2=current,
        )
        return tangent[self.joints.dof_indices]

    def compute_qp_inequalities(
        self, configuration: mink.Configuration, dt: float
    ) -> Constraint:
        del dt  # The total output-frame budget is independent of the IK substep.
        if self.reference_qpos is None:
            return Constraint()
        spent = self.displacement_from_reference(configuration.q)
        upper_remaining = self.budget - spent
        lower_remaining = self.budget + spent
        return Constraint(
            G=np.vstack([self.projection_matrix, -self.projection_matrix]),
            h=np.hstack([upper_remaining, lower_remaining]),
        )


class SoftJointLimitTask(Task):
    """Piecewise-quadratic inward objective inside a configurable limit margin."""

    def __init__(
        self,
        model: mujoco.MjModel,
        cost: float,
        margin_fraction: float,
        min_margin: float = 0.0,
        gain: float = 1.0,
    ) -> None:
        if not np.isfinite(cost) or cost < 0.0:
            raise ValueError("cost must be finite and >= 0")
        if not np.isfinite(margin_fraction) or not 0.0 <= margin_fraction < 0.5:
            raise ValueError("margin_fraction must be in [0, 0.5)")
        if not np.isfinite(min_margin) or min_margin < 0.0:
            raise ValueError("min_margin must be finite and >= 0")
        super().__init__(
            cost=np.full(model.nv, float(cost), dtype=np.float64),
            gain=gain,
            lm_damping=0.0,
        )
        self.model = model
        self.joints = _limited_scalar_joints(model)
        requested_margin = np.maximum(
            margin_fraction * (self.joints.upper - self.joints.lower), min_margin
        )
        half_range = 0.5 * (self.joints.upper - self.joints.lower)
        if np.any(requested_margin >= half_range):
            names = [
                self.joints.names[i]
                for i in np.flatnonzero(requested_margin >= half_range)
            ]
            raise ValueError(f"Soft margin collapses the range for joints: {names}")
        self.margin = requested_margin
        self.soft_lower = self.joints.lower + self.margin
        self.soft_upper = self.joints.upper - self.margin

    def _error_and_active(self, configuration: mink.Configuration) -> tuple[np.ndarray, np.ndarray]:
        q = np.asarray(configuration.q)[self.joints.qpos_indices]
        target = np.clip(q, self.soft_lower, self.soft_upper)
        joint_error = q - target
        active = joint_error != 0.0
        error = np.zeros(configuration.nv, dtype=np.float64)
        error[self.joints.dof_indices] = joint_error
        return error, active

    def active_joint_names(self, configuration: mink.Configuration) -> tuple[str, ...]:
        _, active = self._error_and_active(configuration)
        return tuple(name for name, flag in zip(self.joints.names, active) if flag)

    def compute_error(self, configuration: mink.Configuration) -> np.ndarray:
        return self._error_and_active(configuration)[0]

    def compute_jacobian(self, configuration: mink.Configuration) -> np.ndarray:
        _, active = self._error_and_active(configuration)
        jacobian = np.zeros((configuration.nv, configuration.nv), dtype=np.float64)
        active_dofs = self.joints.dof_indices[active]
        jacobian[active_dofs, active_dofs] = 1.0
        return jacobian


@dataclass(frozen=True)
class TemporalFrameDiagnostic:
    frame_index: int
    trust_region_enabled: bool
    stage1_solve_count: int
    stage2_solve_count: int
    stage1_error_before: float | None
    stage1_error_after: float | None
    stage2_error_before: float | None
    stage2_error_after: float | None
    soft_limit_active_before: int
    soft_limit_active_after: int
    max_abs_joint_step_rad: float | None
    max_joint_velocity_rad_s: float | None
    max_trust_region_ratio: float | None
    trust_region_boundary_joint_count: int


class TemporalGeneralMotionRetargeting(GeneralMotionRetargeting):
    """GMR A1 with a frame-level trust region and two temporal soft objectives."""

    def __init__(self, *args: Any, temporal_config: TemporalGMRConfig, **kwargs: Any) -> None:
        if kwargs.get("use_velocity_limit", False):
            raise ValueError(
                "Do not combine Temporal-GMR with GMR's per-substep velocity limit"
            )
        kwargs["use_velocity_limit"] = False
        super().__init__(*args, **kwargs)
        self.temporal_config = temporal_config
        self.frame_velocity_limit = WholeFrameVelocityLimit(
            self.model,
            max_velocity=temporal_config.max_joint_velocity_rad_s,
            frame_dt=temporal_config.frame_dt,
        )
        self.previous_posture_task = mink.PostureTask(
            self.model, cost=temporal_config.previous_posture_cost
        )
        self.soft_limit_task = SoftJointLimitTask(
            self.model,
            cost=temporal_config.soft_limit_cost,
            margin_fraction=temporal_config.soft_limit_margin_fraction,
            min_margin=temporal_config.soft_limit_min_margin_rad,
        )
        self.previous_output_qpos: np.ndarray | None = None
        self.frame_diagnostics: list[TemporalFrameDiagnostic] = []

    @property
    def limited_joint_names(self) -> tuple[str, ...]:
        return self.frame_velocity_limit.joints.names

    def _solve_stage(self, base_tasks: list[Any], error_fn: Any) -> tuple[int, float, float]:
        tasks = [*base_tasks, self.previous_posture_task, self.soft_limit_task]
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

    def retarget(self, human_data: Any, offset_to_ground: bool = False) -> np.ndarray:
        if not self.temporal_config.enabled:
            return super().retarget(human_data, offset_to_ground)

        self.update_targets(human_data, offset_to_ground)
        previous = (
            None
            if self.previous_output_qpos is None
            else self.previous_output_qpos.copy()
        )
        self.frame_velocity_limit.set_reference(previous)
        if previous is None:
            # PostureTask requires a target even though the first frame must not
            # inherit a fictitious temporal target. Zero cost disables it exactly.
            self.previous_posture_task.set_target(self.configuration.q)
            original_cost = self.previous_posture_task.cost.copy()
            self.previous_posture_task.set_cost(0.0)
        else:
            self.previous_posture_task.set_target(previous)
            original_cost = None

        soft_before = len(self.soft_limit_task.active_joint_names(self.configuration))
        stage1_count = stage2_count = 0
        stage1_before = stage1_after = stage2_before = stage2_after = None
        try:
            if self.use_ik_match_table1:
                stage1_count, stage1_before, stage1_after = self._solve_stage(
                    self.tasks1, self.error1
                )
            if self.use_ik_match_table2:
                stage2_count, stage2_before, stage2_after = self._solve_stage(
                    self.tasks2, self.error2
                )
        finally:
            if original_cost is not None:
                self.previous_posture_task.set_cost(original_cost)

        output = self.configuration.data.qpos.copy()
        if not np.isfinite(output).all():
            raise RuntimeError("Temporal-GMR produced non-finite qpos")

        if previous is None:
            max_step = max_velocity = max_ratio = None
            boundary_count = 0
        else:
            step = self.frame_velocity_limit.displacement_from_reference(output)
            abs_step = np.abs(step)
            ratio = abs_step / self.frame_velocity_limit.budget
            max_step = float(np.max(abs_step))
            max_velocity = float(max_step / self.temporal_config.frame_dt)
            max_ratio = float(np.max(ratio))
            tolerance = self.temporal_config.trust_region_tolerance_rad
            if np.any(abs_step > self.frame_velocity_limit.budget + tolerance):
                joint_index = int(
                    np.argmax(abs_step - self.frame_velocity_limit.budget)
                )
                raise RuntimeError(
                    "Whole-frame velocity trust region was violated: "
                    f"joint={self.limited_joint_names[joint_index]}, "
                    f"step={abs_step[joint_index]:.12g}, "
                    f"budget={self.frame_velocity_limit.budget[joint_index]:.12g}"
                )
            boundary_count = int(np.count_nonzero(ratio >= 1.0 - 1e-6))

        diagnostic = TemporalFrameDiagnostic(
            frame_index=len(self.frame_diagnostics),
            trust_region_enabled=previous is not None,
            stage1_solve_count=stage1_count,
            stage2_solve_count=stage2_count,
            stage1_error_before=stage1_before,
            stage1_error_after=stage1_after,
            stage2_error_before=stage2_before,
            stage2_error_after=stage2_after,
            soft_limit_active_before=soft_before,
            soft_limit_active_after=len(
                self.soft_limit_task.active_joint_names(self.configuration)
            ),
            max_abs_joint_step_rad=max_step,
            max_joint_velocity_rad_s=max_velocity,
            max_trust_region_ratio=max_ratio,
            trust_region_boundary_joint_count=boundary_count,
        )
        self.frame_diagnostics.append(diagnostic)
        self.previous_output_qpos = output.copy()
        return output
