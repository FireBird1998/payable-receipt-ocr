#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

from payable_receipt_ocr import ReceiptOcrError, recognize


def _nearest_rank(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    rank = int(math.ceil(quantile * len(ordered))) - 1
    if rank < 0:
        rank = 0
    return ordered[rank]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools/benchmark.py",
        description="Benchmark payable-receipt-ocr recognize() over local images.",
    )
    parser.add_argument("images", nargs="+", type=Path, help="One or more local image paths")
    parser.add_argument("--repetitions", type=int, default=3, help="Repetitions per image (>=1)")
    parser.add_argument("--tessdata-dir", type=Path, help="Optional tessdata directory override")
    parser.add_argument(
        "--runtime-policy",
        choices=("development", "conformant"),
        default="development",
        help="Runtime validation policy used for each run",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.repetitions < 1:
        print("--repetitions must be at least 1", file=sys.stderr)
        return 2

    runs: list[dict[str, Any]] = []
    durations_ms: list[int] = []
    success_count = 0
    failure_count = 0
    conformant_count = 0
    baseline_ids: set[str] = set()
    started = time.time()

    for repetition in range(args.repetitions):
        for image in args.images:
            image_path = image.expanduser().resolve()
            started_ns = time.perf_counter_ns()
            run: dict[str, Any] = {
                "image": str(image_path),
                "repetition": repetition + 1,
                "runtime_policy": args.runtime_policy,
            }
            try:
                result = recognize(
                    image_path,
                    currency="INR",
                    tessdata_dir=args.tessdata_dir,
                    diagnostics=False,
                    runtime_policy=args.runtime_policy,
                )
                duration_ms = int((time.perf_counter_ns() - started_ns) / 1_000_000)
                run.update(
                    {
                        "ok": True,
                        "duration_ms": duration_ms,
                        "evidence_grade": result.evidence_grade,
                        "passes_completed": result.passes_completed,
                        "runtime_conformant": result.runtime.conformant,
                        "runtime_baseline_id": result.runtime.baseline_id,
                    }
                )
                durations_ms.append(duration_ms)
                success_count += 1
                if result.runtime.conformant:
                    conformant_count += 1
                baseline_ids.add(result.runtime.baseline_id)
            except ReceiptOcrError as error:
                duration_ms = int((time.perf_counter_ns() - started_ns) / 1_000_000)
                run.update(
                    {
                        "ok": False,
                        "duration_ms": duration_ms,
                        "error_code": error.code,
                        "error_message": str(error),
                    }
                )
                failure_count += 1
            runs.append(run)

    stats = {
        "count": len(durations_ms),
        "p50_ms": _nearest_rank(durations_ms, 0.50) if durations_ms else None,
        "p95_ms": _nearest_rank(durations_ms, 0.95) if durations_ms else None,
        "p99_ms": _nearest_rank(durations_ms, 0.99) if durations_ms else None,
    }
    total_runs = len(runs)
    eligible = (
        args.runtime_policy == "conformant" and total_runs > 0 and conformant_count == total_runs
    )
    payload = {
        "tool": "payable-receipt-ocr benchmark",
        "started_unix_seconds": started,
        "runtime_policy": args.runtime_policy,
        "repetitions": args.repetitions,
        "images": [str(path.expanduser().resolve()) for path in args.images],
        "passes": {
            "total_runs": total_runs,
            "success_count": success_count,
            "failure_count": failure_count,
            "conformant_count": conformant_count,
        },
        "durations": stats,
        "environment_eligibility": {
            "eligible_for_conformance_reporting": eligible,
            "runtime_baseline_ids": sorted(baseline_ids),
        },
        "runs": runs,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
