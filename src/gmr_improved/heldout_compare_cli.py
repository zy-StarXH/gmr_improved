from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .heldout_compare import compare_heldout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temporal-gmr-heldout-compare")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--a0-summary", required=True, type=Path)
    parser.add_argument("--a1-summary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = compare_heldout(
        args.config, args.a0_summary, args.a1_summary, args.output_dir
    )
    print(json.dumps({"summary": str(summary)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

