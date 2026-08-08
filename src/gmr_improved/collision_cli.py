"""CLI for A2 Collision-GMR generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collision_experiment import run_collision_retargeting


def main() -> None:
    parser = argparse.ArgumentParser(prog="collision-gmr")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--motions", help="Comma-separated names for a non-formal smoke run")
    parser.add_argument("--max-frames", type=int, help="Prefix length for a non-formal smoke run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    motions = (
        tuple(item.strip() for item in args.motions.split(",") if item.strip())
        if args.motions
        else None
    )
    result = run_collision_retargeting(
        args.config,
        args.output_dir,
        motions=motions,
        max_frames=args.max_frames,
        progress=None if args.json else print,
    )
    print(json.dumps({
        "output_dir": str(result.output_dir),
        "catalog": str(result.catalog_csv),
        "manifest": str(result.manifest_json),
        "motion_count": result.motion_count,
        "frame_count": result.frame_count,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
