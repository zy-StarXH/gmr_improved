from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .analysis import finalize_visual_review, run_analysis, verify_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gmr-improved")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze-baseline", help="Analyze the frozen Step-10 GMR cohort without using its composite score."
    )
    analyze.add_argument("--config", required=True, type=Path)
    analyze.add_argument("--output-dir", required=True, type=Path)
    analyze.add_argument("--json", action="store_true")

    verify = subparsers.add_parser("verify-manifest", help="Independently verify an analysis manifest.")
    verify.add_argument("--manifest", required=True, type=Path)

    finalize = subparsers.add_parser(
        "finalize-review", help="Validate and merge the frozen case catalog with structured review."
    )
    finalize.add_argument("--case-catalog", required=True, type=Path)
    finalize.add_argument("--review", required=True, type=Path)
    finalize.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "analyze-baseline":
        result = run_analysis(args.config, args.output_dir)
        payload = {
            "output_dir": str(result.output_dir),
            "manifest": str(result.manifest),
            "evidence_summary": str(result.evidence_summary),
            "case_catalog": str(result.case_catalog),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0
    if args.command == "verify-manifest":
        payload = verify_manifest(args.manifest)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload["ok"] else 1
    if args.command == "finalize-review":
        path = finalize_visual_review(args.case_catalog, args.review, args.output)
        print(json.dumps({"output": str(path)}, ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
