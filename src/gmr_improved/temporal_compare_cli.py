from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .temporal_compare import compare_temporal_results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temporal-gmr-compare")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--temporal-summary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    summary = compare_temporal_results(
        args.config, args.temporal_summary, args.output_dir
    )
    print(json.dumps({"summary": str(summary)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

