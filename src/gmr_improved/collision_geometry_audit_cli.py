from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .collision_geometry_audit import audit_collision_geometry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collision-gmr-geometry-audit")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--a1-dir", required=True, type=Path)
    parser.add_argument("--a2-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    output = audit_collision_geometry(
        args.model, args.pairs, args.a1_dir, args.a2_dir, args.output_dir
    )
    print(json.dumps({"audit": str(output)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
