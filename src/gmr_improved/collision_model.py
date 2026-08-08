"""Derived named-geom model and audited non-neighbour collision pairs for I1."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mink
import mujoco
import numpy as np


DEFAULT_HAND_PATTERNS = (
    "left_wrist",
    "right_wrist",
    "left_rubber_hand",
    "right_rubber_hand",
)


@dataclass(frozen=True)
class CollisionAuditParameters:
    minimum_tree_distance: int = 3
    minimum_distance_m: float = 0.005
    detection_distance_m: float = 0.020
    gain: float = 0.85
    bound_relaxation: float = 0.0
    broadphase: bool = True
    hand_patterns: tuple[str, ...] = DEFAULT_HAND_PATTERNS
    fk_sample_count: int = 16
    fk_seed: int = 20260806

    def validate(self) -> None:
        if self.minimum_tree_distance < 2:
            raise ValueError("minimum_tree_distance must be at least 2")
        if self.minimum_distance_m < 0.0:
            raise ValueError("minimum_distance_m must be non-negative")
        if self.detection_distance_m <= self.minimum_distance_m:
            raise ValueError("detection_distance_m must exceed minimum_distance_m")
        if not 0.0 < self.gain <= 1.0:
            raise ValueError("gain must be in (0, 1]")
        if self.bound_relaxation != 0.0:
            raise ValueError("I1 preregistration requires zero bound relaxation")
        if not self.hand_patterns:
            raise ValueError("hand_patterns must not be empty")
        if self.fk_sample_count < 2:
            raise ValueError("fk_sample_count must be at least 2")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_empty(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError(f"Output directory must be new or empty: {path}")
    else:
        path.mkdir(parents=True)


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return cleaned or "unnamed"


def generate_named_geom_xml(source_xml: Path, destination_xml: Path) -> int:
    """Copy XML semantics while naming every unnamed geom deterministically."""
    source_xml = source_xml.resolve()
    if destination_xml.exists():
        raise FileExistsError(f"Refusing to overwrite derived XML: {destination_xml}")
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(source_xml, parser=parser)
    root = tree.getroot()
    compiler = root.find("compiler")
    if compiler is None:
        raise ValueError("Source XML has no compiler element")
    meshdir = compiler.get("meshdir")
    if meshdir:
        mesh_path = Path(meshdir)
        if not mesh_path.is_absolute():
            mesh_path = (source_xml.parent / mesh_path).resolve()
        compiler.set("meshdir", str(mesh_path))

    existing = {
        geom.get("name") for geom in root.iter("geom") if geom.get("name")
    }
    assigned = 0

    def name_body_geoms(body: ET.Element, body_name: str) -> None:
        nonlocal assigned
        local_index = 0
        for geom in body.findall("geom"):
            if not geom.get("name"):
                candidate = f"i1_{_safe_name(body_name)}_geom_{local_index:02d}"
                if candidate in existing:
                    raise ValueError(f"Generated duplicate geom name: {candidate}")
                geom.set("name", candidate)
                existing.add(candidate)
                assigned += 1
            local_index += 1
        for child in body.findall("body"):
            child_name = child.get("name")
            if not child_name:
                raise ValueError("All robot bodies must be named for pair audit")
            name_body_geoms(child, child_name)

    worldbody = root.find("worldbody")
    if worldbody is None:
        raise ValueError("Source XML has no worldbody")
    world_index = 0
    for geom in worldbody.findall("geom"):
        if not geom.get("name"):
            candidate = f"i1_world_geom_{world_index:02d}"
            if candidate in existing:
                raise ValueError(f"Generated duplicate geom name: {candidate}")
            geom.set("name", candidate)
            existing.add(candidate)
            assigned += 1
        world_index += 1
    for body in worldbody.findall("body"):
        body_name = body.get("name")
        if not body_name:
            raise ValueError("All top-level bodies must be named")
        name_body_geoms(body, body_name)

    ET.indent(tree, space="  ")
    destination_xml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(destination_xml, encoding="utf-8", xml_declaration=True)
    return assigned


def _object_names(model: mujoco.MjModel, object_type: mujoco.mjtObj, count: int) -> list[str | None]:
    return [mujoco.mj_id2name(model, object_type, index) for index in range(count)]


def _compare_array(
    original: mujoco.MjModel,
    derived: mujoco.MjModel,
    attribute: str,
    mismatches: list[str],
) -> None:
    if not hasattr(original, attribute) or not hasattr(derived, attribute):
        mismatches.append(f"missing_model_attribute:{attribute}")
        return
    left = np.asarray(getattr(original, attribute))
    right = np.asarray(getattr(derived, attribute))
    if left.shape != right.shape:
        mismatches.append(f"model_array_shape:{attribute}:{left.shape}!={right.shape}")
        return
    if np.issubdtype(left.dtype, np.floating):
        if not np.array_equal(left, right):
            mismatches.append(
                f"model_array_value:{attribute}:max_abs={float(np.max(np.abs(left-right)))}"
            )
    elif not np.array_equal(left, right):
        mismatches.append(f"model_array_value:{attribute}")


MODEL_ARRAYS = (
    "qpos0",
    "body_parentid",
    "body_rootid",
    "body_weldid",
    "body_pos",
    "body_quat",
    "body_ipos",
    "body_iquat",
    "body_mass",
    "body_inertia",
    "jnt_type",
    "jnt_bodyid",
    "jnt_qposadr",
    "jnt_dofadr",
    "jnt_pos",
    "jnt_axis",
    "jnt_range",
    "jnt_limited",
    "dof_bodyid",
    "dof_jntid",
    "dof_parentid",
    "geom_type",
    "geom_bodyid",
    "geom_contype",
    "geom_conaffinity",
    "geom_group",
    "geom_dataid",
    "geom_matid",
    "geom_pos",
    "geom_quat",
    "geom_size",
    "geom_friction",
    "geom_margin",
    "geom_gap",
    "geom_rgba",
    "site_bodyid",
    "site_pos",
    "site_quat",
    "site_size",
    "actuator_trnid",
    "actuator_ctrlrange",
    "actuator_forcerange",
)


def _sample_qpos(model: mujoco.MjModel, count: int, seed: int) -> Iterable[np.ndarray]:
    yield model.qpos0.copy()
    rng = np.random.default_rng(seed)
    for _ in range(count - 1):
        qpos = model.qpos0.copy()
        for joint_id in range(model.njnt):
            joint_type = int(model.jnt_type[joint_id])
            address = int(model.jnt_qposadr[joint_id])
            if joint_type == int(mujoco.mjtJoint.mjJNT_FREE):
                qpos[address : address + 3] += rng.uniform(-0.2, 0.2, 3)
                quat = rng.normal(size=4)
                qpos[address + 3 : address + 7] = quat / np.linalg.norm(quat)
            elif joint_type == int(mujoco.mjtJoint.mjJNT_BALL):
                quat = rng.normal(size=4)
                qpos[address : address + 4] = quat / np.linalg.norm(quat)
            else:
                if bool(model.jnt_limited[joint_id]):
                    low, high = model.jnt_range[joint_id]
                    qpos[address] = rng.uniform(low, high)
                else:
                    qpos[address] += rng.uniform(-0.5, 0.5)
        yield qpos


def verify_model_equivalence(
    source_xml: Path,
    derived_xml: Path,
    *,
    sample_count: int,
    seed: int,
) -> dict[str, Any]:
    original = mujoco.MjModel.from_xml_path(str(source_xml))
    derived = mujoco.MjModel.from_xml_path(str(derived_xml))
    mismatches: list[str] = []
    dimensions = ("nq", "nv", "nbody", "njnt", "ngeom", "nsite", "nu", "nmesh")
    for name in dimensions:
        if int(getattr(original, name)) != int(getattr(derived, name)):
            mismatches.append(f"dimension:{name}")
    if original.opt.timestep != derived.opt.timestep:
        mismatches.append("option:timestep")
    if not np.array_equal(original.opt.gravity, derived.opt.gravity):
        mismatches.append("option:gravity")
    for attribute in MODEL_ARRAYS:
        _compare_array(original, derived, attribute, mismatches)

    named_types = (
        (mujoco.mjtObj.mjOBJ_BODY, original.nbody),
        (mujoco.mjtObj.mjOBJ_JOINT, original.njnt),
        (mujoco.mjtObj.mjOBJ_SITE, original.nsite),
        (mujoco.mjtObj.mjOBJ_ACTUATOR, original.nu),
        (mujoco.mjtObj.mjOBJ_MESH, original.nmesh),
    )
    for object_type, count in named_types:
        if _object_names(original, object_type, count) != _object_names(derived, object_type, count):
            mismatches.append(f"object_names:{int(object_type)}")
    derived_geom_names = _object_names(derived, mujoco.mjtObj.mjOBJ_GEOM, derived.ngeom)
    if any(name is None for name in derived_geom_names):
        mismatches.append("derived_geom_names:unnamed")
    if len(set(derived_geom_names)) != len(derived_geom_names):
        mismatches.append("derived_geom_names:duplicate")
    if derived_geom_names[0] != "floor":
        mismatches.append("derived_geom_names:floor_changed")

    data_original = mujoco.MjData(original)
    data_derived = mujoco.MjData(derived)
    fk_fields = ("xpos", "xquat", "xmat", "geom_xpos", "geom_xmat", "site_xpos", "site_xmat")
    max_fk_error = {name: 0.0 for name in fk_fields}
    for sample_index, qpos in enumerate(_sample_qpos(original, sample_count, seed)):
        data_original.qpos[:] = qpos
        data_derived.qpos[:] = qpos
        mujoco.mj_forward(original, data_original)
        mujoco.mj_forward(derived, data_derived)
        for field in fk_fields:
            left = np.asarray(getattr(data_original, field))
            right = np.asarray(getattr(data_derived, field))
            error = float(np.max(np.abs(left - right))) if left.size else 0.0
            max_fk_error[field] = max(max_fk_error[field], error)
            if error > 1e-12:
                mismatches.append(f"fk:{sample_index}:{field}:{error}")

    return {
        "ok": not mismatches,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "dimensions": {name: int(getattr(derived, name)) for name in dimensions},
        "sample_count": sample_count,
        "seed": seed,
        "max_fk_abs_error": max_fk_error,
        "derived_geom_name_count": len(derived_geom_names),
        "derived_unique_geom_name_count": len(set(derived_geom_names)),
    }


def body_tree_distance(model: mujoco.MjModel, body_a: int, body_b: int) -> int:
    ancestors: dict[int, int] = {}
    current = body_a
    distance = 0
    while True:
        ancestors[current] = distance
        if current == 0:
            break
        current = int(model.body_parentid[current])
        distance += 1
    current = body_b
    distance = 0
    while current not in ancestors:
        current = int(model.body_parentid[current])
        distance += 1
    return ancestors[current] + distance


def _passes_collision_filter(model: mujoco.MjModel, geom_a: int, geom_b: int) -> bool:
    return bool(
        (int(model.geom_contype[geom_a]) & int(model.geom_conaffinity[geom_b]))
        or (int(model.geom_contype[geom_b]) & int(model.geom_conaffinity[geom_a]))
    )


def audit_collision_pairs(
    derived_xml: Path,
    parameters: CollisionAuditParameters,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[tuple[str, ...], tuple[str, ...]]]]:
    parameters.validate()
    model = mujoco.MjModel.from_xml_path(str(derived_xml))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    exclusions = {
        "world_or_floor": 0,
        "same_body": 0,
        "allowed_hand_contact": 0,
        "tree_distance_below_minimum": 0,
        "contype_conaffinity_filter": 0,
    }
    records: list[dict[str, Any]] = []
    mink_pairs: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    fromto = np.empty(6, dtype=np.float64)
    for geom_a in range(model.ngeom):
        for geom_b in range(geom_a + 1, model.ngeom):
            body_a = int(model.geom_bodyid[geom_a])
            body_b = int(model.geom_bodyid[geom_b])
            if body_a == 0 or body_b == 0:
                exclusions["world_or_floor"] += 1
                continue
            if body_a == body_b:
                exclusions["same_body"] += 1
                continue
            body_name_a = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_a)
            body_name_b = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_b)
            if any(
                pattern in body_name
                for pattern in parameters.hand_patterns
                for body_name in (body_name_a, body_name_b)
            ):
                exclusions["allowed_hand_contact"] += 1
                continue
            tree_distance = body_tree_distance(model, body_a, body_b)
            if tree_distance < parameters.minimum_tree_distance:
                exclusions["tree_distance_below_minimum"] += 1
                continue
            if not _passes_collision_filter(model, geom_a, geom_b):
                exclusions["contype_conaffinity_filter"] += 1
                continue
            geom_name_a = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_a)
            geom_name_b = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_b)
            neutral_distance = float(
                mujoco.mj_geomDistance(model, data, geom_a, geom_b, 1.0, fromto)
            )
            records.append(
                {
                    "geom_a_id": geom_a,
                    "geom_a_name": geom_name_a,
                    "body_a_id": body_a,
                    "body_a_name": body_name_a,
                    "geom_b_id": geom_b,
                    "geom_b_name": geom_name_b,
                    "body_b_id": body_b,
                    "body_b_name": body_name_b,
                    "tree_distance": tree_distance,
                    "neutral_distance_m": neutral_distance,
                    "active_at_neutral": neutral_distance < parameters.detection_distance_m,
                    "below_minimum_at_neutral": neutral_distance < parameters.minimum_distance_m,
                }
            )
            mink_pairs.append(((geom_name_a,), (geom_name_b,)))

    if not records:
        raise ValueError("Collision pair audit selected no pairs")
    below_minimum = [row for row in records if row["below_minimum_at_neutral"]]
    if below_minimum:
        raise ValueError(
            f"Neutral model violates preregistered minimum distance for {len(below_minimum)} pairs"
        )
    limit = mink.CollisionAvoidanceLimit(
        model,
        geom_pairs=mink_pairs,
        gain=parameters.gain,
        minimum_distance_from_collisions=parameters.minimum_distance_m,
        collision_detection_distance=parameters.detection_distance_m,
        bound_relaxation=parameters.bound_relaxation,
        broadphase=parameters.broadphase,
    )
    expected = {
        (int(row["geom_a_id"]), int(row["geom_b_id"])) for row in records
    }
    actual = {tuple(sorted(pair)) for pair in limit.geom_id_pairs}
    if actual != expected:
        raise ValueError(
            f"Mink pair expansion mismatch: expected={len(expected)}, actual={len(actual)}"
        )
    body_pairs = {
        tuple(sorted((row["body_a_name"], row["body_b_name"]))) for row in records
    }
    audit = {
        "ok": True,
        "parameters": asdict(parameters),
        "candidate_geom_pair_count": model.ngeom * (model.ngeom - 1) // 2,
        "included_geom_pair_count": len(records),
        "included_body_pair_count": len(body_pairs),
        "exclusion_counts": exclusions,
        "active_at_neutral_count": sum(row["active_at_neutral"] for row in records),
        "below_minimum_at_neutral_count": 0,
        "minimum_neutral_distance_m": min(row["neutral_distance_m"] for row in records),
        "mink_expanded_pair_count": len(actual),
    }
    return audit, records, mink_pairs


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare_collision_model(
    source_xml: str | Path,
    output_dir: str | Path,
    parameters: CollisionAuditParameters | None = None,
) -> Path:
    source = Path(source_xml).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    parameters = parameters or CollisionAuditParameters()
    parameters.validate()
    _prepare_empty(destination)
    derived = destination / "g1_mocap_29dof_collision_named.xml"
    assigned_count = generate_named_geom_xml(source, derived)
    equivalence = verify_model_equivalence(
        source,
        derived,
        sample_count=parameters.fk_sample_count,
        seed=parameters.fk_seed,
    )
    if not equivalence["ok"]:
        raise ValueError(f"Derived model equivalence failed: {equivalence['mismatches']}")
    pair_audit, pair_records, _ = audit_collision_pairs(derived, parameters)

    original = mujoco.MjModel.from_xml_path(str(source))
    named = mujoco.MjModel.from_xml_path(str(derived))
    name_rows = []
    for geom_id in range(named.ngeom):
        name_rows.append(
            {
                "geom_id": geom_id,
                "body_name": mujoco.mj_id2name(
                    named, mujoco.mjtObj.mjOBJ_BODY, int(named.geom_bodyid[geom_id])
                ),
                "original_geom_name": mujoco.mj_id2name(
                    original, mujoco.mjtObj.mjOBJ_GEOM, geom_id
                ) or "",
                "derived_geom_name": mujoco.mj_id2name(
                    named, mujoco.mjtObj.mjOBJ_GEOM, geom_id
                ),
            }
        )
    pair_csv = destination / "collision_pairs.csv"
    name_csv = destination / "geom_name_map.csv"
    _write_csv(pair_csv, pair_records)
    _write_csv(name_csv, name_rows)
    audit_payload = {
        "schema_version": 1,
        "source_xml": {"path": str(source), "sha256": sha256_file(source)},
        "derived_xml": {"path": str(derived), "sha256": sha256_file(derived)},
        "assigned_geom_name_count": assigned_count,
        "model_equivalence": equivalence,
        "pair_audit": pair_audit,
    }
    audit_path = destination / "collision_model_audit.json"
    audit_path.write_text(
        json.dumps(audit_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs = [derived, pair_csv, name_csv, audit_path]
    manifest = {
        "schema_version": 1,
        "stage": "I1_collision_model_and_pair_audit",
        "complete": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_xml": {"path": str(source), "sha256": sha256_file(source)},
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "outputs": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in outputs
        ],
    }
    manifest_path = destination / "collision_model_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path
