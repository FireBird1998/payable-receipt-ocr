#!/usr/bin/env python3
"""Exploratory local accuracy and latency checks through the public OCR interface."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from payable_receipt_ocr import ReceiptOcrError, recognize


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    image: Path
    category: str = "uncategorized"
    labelled: bool = False
    expected_total: str | None = None
    expected_currency: str | None = None


def _nonempty_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def load_manifest(path: Path) -> list[BenchmarkCase]:
    """Validate all labels and paths before starting any OCR work."""
    path = path.expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("manifest must be an object containing a cases array")
    if not payload["cases"]:
        raise ValueError("manifest cases must not be empty")
    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(payload["cases"]):
        if not isinstance(record, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_id = _nonempty_string(record, "id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate id: {case_id}")
        seen_ids.add(case_id)
        image = Path(_nonempty_string(record, "image")).expanduser()
        image = (path.parent / image).resolve()
        if not image.is_file():
            raise ValueError(f"cases[{index}] image must identify an existing file")
        if "expected_total" not in record or "expected_currency" not in record:
            raise ValueError(f"cases[{index}] requires expected_total and expected_currency")
        total, currency = record["expected_total"], record["expected_currency"]
        if total is None:
            if currency is not None:
                raise ValueError("expected_currency must be null when expected_total is null")
        elif (
            not isinstance(total, str)
            or re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", total) is None
        ):
            raise ValueError("expected_total must be a nonnegative canonical two-decimal string")
        elif currency != "INR":
            raise ValueError("expected_currency must be INR when expected_total is an amount")
        category = _nonempty_string(record, "category") if "category" in record else "uncategorized"
        cases.append(BenchmarkCase(case_id, image, category, True, total, currency))
    return cases


def _nearest_rank(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, int(math.ceil(quantile * len(ordered))) - 1)]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools/benchmark.py",
        description="Explore local OCR accuracy and latency; this is not a release holdout gate.",
    )
    parser.add_argument("images", nargs="*", type=Path, help="One or more local image paths")
    parser.add_argument(
        "--manifest", type=Path, help="JSON development cases with expected results"
    )
    parser.add_argument("--output", type=Path, help="Also save the JSON report to this local file")
    parser.add_argument("--repetitions", type=int, default=3, help="Repetitions per image (>=1)")
    parser.add_argument("--tessdata-dir", type=Path, help="Optional tessdata directory override")
    parser.add_argument(
        "--runtime-policy",
        choices=("development", "conformant"),
        default="development",
        help="Runtime validation policy used for each run",
    )
    return parser


def _accuracy(runs: list[dict[str, Any]]) -> dict[str, Any]:
    labelled = [run for run in runs if "exact_match" in run]
    exact_count = sum(run["exact_match"] for run in labelled)
    return {
        "labelled_run_count": len(labelled),
        "exact_match_count": exact_count,
        "exact_match_rate": exact_count / len(labelled) if labelled else None,
        "false_strong_count": (
            sum(run["evidence_grade"] == "strong" and not run["exact_match"] for run in labelled)
            if labelled
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.repetitions < 1:
        print("--repetitions must be at least 1", file=sys.stderr)
        return 2
    if bool(args.manifest) == bool(args.images):
        print("provide either images or --manifest, exclusively", file=sys.stderr)
        return 2
    try:
        cases = (
            load_manifest(args.manifest)
            if args.manifest
            else [
                BenchmarkCase(f"image-{index + 1}", image.expanduser().resolve())
                for index, image in enumerate(args.images)
            ]
        )
    except (OSError, ValueError) as error:
        print(f"Invalid manifest: {error}", file=sys.stderr)
        return 2

    runs: list[dict[str, Any]] = []
    started = time.time()
    batch_started_ns = time.perf_counter_ns()
    baseline_ids: set[str] = set()
    for repetition in range(args.repetitions):
        for case in cases:
            run: dict[str, Any] = {
                "case_id": case.case_id,
                "image": str(case.image),
                "category": case.category,
                "repetition": repetition + 1,
                "runtime_policy": args.runtime_policy,
                "observed_total": None,
                "observed_currency": None,
                "evidence_grade": "none",
                "requires_confirmation": None,
                "authorizes_persistence": None,
                "degraded": None,
                "deadline_exceeded": None,
            }
            started_ns = time.perf_counter_ns()
            try:
                result = recognize(
                    case.image,
                    currency="INR",
                    tessdata_dir=args.tessdata_dir,
                    diagnostics=False,
                    runtime_policy=args.runtime_policy,
                )
                run.update(
                    {
                        "ok": True,
                        "observed_total": format(result.total, ".2f")
                        if result.total is not None
                        else None,
                        "observed_currency": result.currency,
                        "evidence_grade": result.evidence_grade,
                        "warning_codes": [warning.code for warning in result.warnings],
                        "requires_confirmation": result.requires_confirmation,
                        "authorizes_persistence": result.authorizes_persistence,
                        "passes_completed": result.passes_completed,
                        "degraded": result.degraded,
                        "deadline_exceeded": result.deadline_exceeded,
                        "runtime_conformant": result.runtime.conformant,
                        "runtime_baseline_id": result.runtime.baseline_id,
                    }
                )
                baseline_ids.add(result.runtime.baseline_id)
                if case.labelled:
                    expected = (
                        Decimal(case.expected_total) if case.expected_total is not None else None
                    )
                    run["exact_match"] = (
                        result.total == expected and result.currency == case.expected_currency
                    )
            except ReceiptOcrError as error:
                run.update(
                    {
                        "ok": False,
                        "error_code": error.code,
                        "error_message": str(error),
                        "warning_codes": [f"error:{error.code}"],
                    }
                )
                if case.labelled:
                    run["exact_match"] = False
            run["duration_ms"] = int((time.perf_counter_ns() - started_ns) / 1_000_000)
            if case.labelled:
                run["expected_total"] = case.expected_total
                run["expected_currency"] = case.expected_currency
            runs.append(run)

    wall_duration_ms = int((time.perf_counter_ns() - batch_started_ns) / 1_000_000)
    durations_ms = [run["duration_ms"] for run in runs]
    returned = [run for run in runs if run["ok"]]
    failures = [run for run in runs if not run["ok"]]
    conformant_count = sum(run["runtime_conformant"] for run in returned)
    confirmation_count = sum(run["requires_confirmation"] is True for run in returned)
    invariant_violations = sum(
        run["requires_confirmation"] is not True or run["authorizes_persistence"] is not False
        for run in returned
    )
    summary = {
        **_accuracy(runs),
        "case_count": len(cases),
        "no_suggestion_count": sum(run["observed_total"] is None for run in returned),
        "error_count": len(failures),
        "error_counts": dict(Counter(run["error_code"] for run in failures)),
        "confirmation_required_count": confirmation_count,
        "confirmation_rate": confirmation_count / len(returned) if returned else None,
        "confirmation_invariant_violations": invariant_violations,
        "degraded_count": sum(run["degraded"] for run in returned),
        "deadline_exceeded_count": sum(run["deadline_exceeded"] for run in returned),
        "per_category": {
            category: _accuracy([run for run in runs if run["category"] == category])
            for category in sorted({case.category for case in cases})
        },
    }
    payload = {
        "tool": "payable-receipt-ocr benchmark",
        "evaluation_kind": "exploratory_development",
        "started_unix_seconds": started,
        "runtime_policy": args.runtime_policy,
        "repetitions": args.repetitions,
        "images": [str(case.image) for case in cases],
        "passes": {
            "total_runs": len(runs),
            "success_count": len(returned),
            "failure_count": len(failures),
            "conformant_count": conformant_count,
        },
        "durations": {
            "count": len(durations_ms),
            "p50_ms": _nearest_rank(durations_ms, 0.50),
            "p95_ms": _nearest_rank(durations_ms, 0.95),
            "p99_ms": _nearest_rank(durations_ms, 0.99),
            "wall_duration_ms": wall_duration_ms,
        },
        "summary": summary,
        "environment_eligibility": {
            "eligible_for_conformance_reporting": (
                args.runtime_policy == "conformant" and conformant_count == len(runs)
            ),
            "eligible_for_release_gate": False,
            "runtime_baseline_ids": sorted(baseline_ids),
        },
        "runs": runs,
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        try:
            output = args.output.expanduser()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded + "\n", encoding="utf-8")
        except OSError as error:
            print(f"Unable to write report: {error}", file=sys.stderr)
            return 2
    print(encoded)
    mismatches = summary["labelled_run_count"] - summary["exact_match_count"]
    return 1 if failures or mismatches or invariant_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
