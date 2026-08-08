from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .viewer_compat import create_viewer_compatible_copy


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gmr-viewer-compat")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            create_viewer_compatible_copy(args.input, args.output),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
