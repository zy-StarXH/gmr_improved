from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .contact import ContactGMRConfig
from .contact_input_audit import audit_contact_inputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contact-gmr-input-audit")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--anchor-xy-cost", type=float)
    parser.add_argument("--anchor-z-cost", type=float)
    args = parser.parse_args(argv)
    if (args.anchor_xy_cost is None) != (args.anchor_z_cost is None):
        parser.error("--anchor-xy-cost and --anchor-z-cost must be provided together")
    config = (
        ContactGMRConfig(
            anchor_xy_cost=args.anchor_xy_cost,
            anchor_z_cost=args.anchor_z_cost,
        )
        if args.anchor_xy_cost is not None
        else None
    )
    output = audit_contact_inputs(args.catalog, args.output_dir, config=config)
    print(json.dumps({"audit": str(output)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
