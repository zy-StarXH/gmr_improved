from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .i1_delivery import create_delivery


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collision-gmr-i1-finalize")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args(argv)
    manifest, audit = create_delivery(args.root, args.manifest, args.audit)
    print(json.dumps({"manifest": str(manifest), "audit": str(audit)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
