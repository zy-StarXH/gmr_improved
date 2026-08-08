from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .temporal_audit import audit_temporal_run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temporal-gmr-audit")
    parser.add_argument("--generation-manifest", required=True, type=Path)
    parser.add_argument("--quality-manifest", required=True, type=Path)
    parser.add_argument("--comparison-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit_temporal_run(
        args.generation_manifest, args.quality_manifest, args.comparison_manifest
    )
    if args.output.exists():
        raise ValueError(f"Audit output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

