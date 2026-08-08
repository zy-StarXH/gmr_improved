from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .collision_compare import compare_collision_results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collision-gmr-compare")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--a1-summary", required=True, type=Path)
    parser.add_argument("--a2-summary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = compare_collision_results(
        args.config, args.a1_summary, args.a2_summary, args.output_dir
    )
    print(json.dumps({"summary": str(summary)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
