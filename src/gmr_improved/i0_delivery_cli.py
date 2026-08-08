"""CLI for final I0 delivery creation and verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .i0_delivery import create_delivery, sha256_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--audit", required=True)
    args = parser.parse_args()
    manifest, audit = create_delivery(
        Path(args.project_root), Path(args.manifest), Path(args.audit)
    )
    print(json.dumps({
        "manifest": str(manifest),
        "manifest_sha256": sha256_file(manifest),
        "audit": str(audit),
        "audit_sha256": sha256_file(audit),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
