"""CLI for the I1 named model and collision-pair audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collision_model import CollisionAuditParameters, prepare_collision_model


def main() -> None:
    parser = argparse.ArgumentParser(prog="collision-gmr-prepare-model")
    parser.add_argument("--source-xml", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = prepare_collision_model(
        args.source_xml,
        args.output_dir,
        CollisionAuditParameters(),
    )
    print(json.dumps({"manifest": str(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
