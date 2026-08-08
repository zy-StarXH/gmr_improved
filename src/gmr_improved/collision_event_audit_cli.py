from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .collision_event_audit import audit_collision_event_coverage


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collision-gmr-event-audit")
    parser.add_argument("--pairs", required=True, type=Path)
    parser.add_argument("--a1-events", required=True, type=Path)
    parser.add_argument("--a2-events", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    output = audit_collision_event_coverage(
        args.pairs, args.a1_events, args.a2_events, args.output_dir
    )
    print(json.dumps({"audit": str(output)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
