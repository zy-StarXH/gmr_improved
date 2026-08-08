"""CLI for the final I0 held-out visualization packet."""

from __future__ import annotations

import argparse
import json

from .heldout_visualization_v3 import generate_v3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison-dir", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--a0-quality-dir", required=True)
    parser.add_argument("--a1-quality-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    manifest = generate_v3(
        args.comparison_dir, args.audit, args.a0_quality_dir,
        args.a1_quality_dir, args.output_dir,
    )
    print(json.dumps({"manifest": str(manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
