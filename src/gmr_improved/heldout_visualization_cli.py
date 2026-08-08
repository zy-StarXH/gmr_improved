from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .heldout_visualization import generate_heldout_visualizations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temporal-gmr-heldout-visualize")
    parser.add_argument("--comparison-dir", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--a0-quality-dir", required=True, type=Path)
    parser.add_argument("--a1-quality-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest = generate_heldout_visualizations(
        args.comparison_dir,
        args.audit,
        args.a0_quality_dir,
        args.a1_quality_dir,
        args.output_dir,
    )
    print(json.dumps({"manifest": str(manifest)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

