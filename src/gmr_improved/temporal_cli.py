"""Command-line entry point kept separate from the hash-frozen Step-3 CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .temporal_experiment import run_temporal_retargeting


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="temporal-gmr")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--motions",
        help="Optional comma-separated motion names for a non-formal smoke run.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="Optional per-motion prefix length for a non-formal smoke run.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    motions = (
        tuple(item.strip() for item in args.motions.split(",") if item.strip())
        if args.motions
        else None
    )
    result = run_temporal_retargeting(
        args.config,
        args.output_dir,
        motions=motions,
        max_frames=args.max_frames,
        progress=None if args.json else print,
    )
    payload = {
        "output_dir": str(result.output_dir),
        "catalog": str(result.catalog_csv),
        "manifest": str(result.manifest_json),
        "motion_count": result.motion_count,
        "frame_count": result.frame_count,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
