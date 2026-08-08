from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .contact_compare import compare_contact_results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contact-gmr-compare")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--a2-summary", required=True, type=Path)
    parser.add_argument("--a3-summary", required=True, type=Path)
    parser.add_argument("--a3-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    output = compare_contact_results(
        args.config,
        args.a2_summary,
        args.a3_summary,
        args.a3_manifest,
        args.output_dir,
    )
    print(json.dumps({"summary": str(output)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
