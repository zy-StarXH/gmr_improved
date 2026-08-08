"""Create non-destructive PKL copies compatible with GMR's MuJoCo viewer."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Any

import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_viewer_compatible_copy(
    source: str | Path, destination: str | Path
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if destination_path.exists():
        raise FileExistsError(f"Refusing to overwrite viewer copy: {destination_path}")
    with source_path.open("rb") as stream:
        payload = pickle.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Motion PKL payload must be a mapping")
    for key in ("fps", "root_pos", "root_rot", "dof_pos"):
        if key not in payload:
            raise ValueError(f"Motion PKL is missing required key: {key}")
    output = dict(payload)
    output.setdefault("local_body_pos", None)
    output.setdefault("link_body_list", None)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_suffix(destination_path.suffix + ".partial")
    with temporary.open("wb") as stream:
        pickle.dump(output, stream, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(destination_path)
    with destination_path.open("rb") as stream:
        roundtrip = pickle.load(stream)
    for key in ("root_pos", "root_rot", "dof_pos"):
        np.testing.assert_array_equal(roundtrip[key], payload[key])
    return {
        "source": str(source_path),
        "source_sha256": sha256_file(source_path),
        "destination": str(destination_path),
        "destination_sha256": sha256_file(destination_path),
        "added_keys": sorted(set(output) - set(payload)),
    }
