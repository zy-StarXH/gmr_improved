from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .heldout_experiment import run_heldout_generation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temporal-gmr-heldout")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--variant", required=True, choices=("a0", "a1"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_heldout_generation(
        args.config,
        args.output_dir,
        args.variant,
        progress=None if args.json else print,
    )
    print(
        json.dumps(
            {
                "variant": result.variant,
                "output_dir": str(result.output_dir),
                "catalog": str(result.catalog_csv),
                "manifest": str(result.manifest_json),
                "motion_count": result.motion_count,
                "frame_count": result.frame_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

