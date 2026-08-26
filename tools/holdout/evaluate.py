#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from payable_receipt_ocr import ReceiptOcrError, recognize

SUPPORTED_APPS = ("blinkit", "swiggy", "zepto")
EXPECTED_CURRENCY = "INR"
MIN_CASES = 300
MIN_CASES_PER_APP = 100


@dataclass(frozen=True)
class HoldoutCase:
    case_id: str
    image_path: Path
    image_sha256: str
    app: str
    capture_type: str
    expected_total: str
    expected_currency: str


class ManifestError(ValueError):
    pass


def _canonical_manifest_sha256(payload: dict[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("manifest_sha256", None)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"manifest field '{key}' must be a non-empty string")
    return value


def _parse_amount(value: str, *, field_name: str) -> Decimal:
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", value) is None:
        raise ManifestError(f"{field_name} must use canonical positive two-decimal form")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ManifestError(f"{field_name} must be an exact decimal string") from error
    if not amount.is_finite() or amount <= 0:
        raise ManifestError(f"{field_name} must be a positive finite amount")
    return amount


def _validate_case_record(case: dict[str, Any], index: int, corpus_root: Path) -> HoldoutCase:
    label = f"cases[{index}]"
    case_id = _require_str(case, "case_id")
    image_relpath = _require_str(case, "image_relpath")
    image_sha256 = _require_str(case, "image_sha256").lower()
    app = _require_str(case, "app").lower()
    capture_type = _require_str(case, "capture_type")
    expected_total = _require_str(case, "expected_total")
    expected_currency = _require_str(case, "expected_currency").upper()

    if app not in SUPPORTED_APPS:
        raise ManifestError(f"{label} app must be one of {SUPPORTED_APPS}")
    if expected_currency != EXPECTED_CURRENCY:
        raise ManifestError(f"{label} expected_currency must be INR")
    _parse_amount(expected_total, field_name=f"{label}.expected_total")
    if len(image_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in image_sha256):
        raise ManifestError(f"{label} image_sha256 must be a lowercase SHA-256 hex digest")

    rel = Path(image_relpath)
    if rel.is_absolute():
        raise ManifestError(f"{label} image_relpath must be relative")
    image_path = (corpus_root / rel).resolve()
    try:
        image_path.relative_to(corpus_root)
    except ValueError as error:
        raise ManifestError(f"{label} image_relpath escapes corpus root") from error
    if not image_path.is_file():
        raise ManifestError(f"{label} image file not found")

    actual_digest = _sha256_file(image_path)
    if actual_digest != image_sha256:
        raise ManifestError(f"{label} image_sha256 does not match file bytes")

    return HoldoutCase(
        case_id=case_id,
        image_path=image_path,
        image_sha256=image_sha256,
        app=app,
        capture_type=capture_type,
        expected_total=expected_total,
        expected_currency=expected_currency,
    )


def load_manifest(
    manifest_path: Path, corpus_root: Path
) -> tuple[dict[str, str], list[HoldoutCase]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")

    manifest_sha256 = _require_str(data, "manifest_sha256").lower()
    if _canonical_manifest_sha256(data) != manifest_sha256:
        raise ManifestError("manifest_sha256 mismatch for canonicalized manifest")

    frozen_at = _require_str(data, "frozen_at")
    try:
        parsed_frozen_at = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ManifestError("manifest field 'frozen_at' must be an ISO-8601 timestamp") from error
    if parsed_frozen_at.tzinfo is None:
        raise ManifestError("manifest field 'frozen_at' must include a timezone")

    metadata = {
        "corpus_version": _require_str(data, "corpus_version"),
        "frozen_at": frozen_at,
        "manifest_sha256": manifest_sha256,
        "runtime_baseline_id": _require_str(data, "runtime_baseline_id"),
    }

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise ManifestError("manifest field 'cases' must be an array")

    cases: list[HoldoutCase] = []
    per_app = {app: 0 for app in SUPPORTED_APPS}
    seen_hashes: set[str] = set()
    seen_case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ManifestError(f"cases[{index}] must be an object")
        case = _validate_case_record(raw_case, index, corpus_root)
        if case.image_sha256 in seen_hashes:
            raise ManifestError("manifest contains duplicate image SHA-256 values")
        if case.case_id in seen_case_ids:
            raise ManifestError("manifest contains duplicate case_id values")
        seen_hashes.add(case.image_sha256)
        seen_case_ids.add(case.case_id)
        per_app[case.app] += 1
        cases.append(case)

    if len(cases) < MIN_CASES:
        raise ManifestError(f"manifest must contain at least {MIN_CASES} cases")
    for app, count in per_app.items():
        if count < MIN_CASES_PER_APP:
            raise ManifestError(
                f"manifest must contain at least {MIN_CASES_PER_APP} cases for app '{app}'"
            )

    return metadata, cases


def _format_total(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _nearest_rank(sorted_values: list[int], quantile: float) -> int:
    rank = int(math.ceil(quantile * len(sorted_values))) - 1
    if rank < 0:
        rank = 0
    return sorted_values[rank]


def evaluate_holdout(
    *, cases: list[HoldoutCase], runtime_policy: str, expected_baseline_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evaluated_cases: list[dict[str, Any]] = []
    durations: list[int] = []
    exact_match_count = 0
    false_strong_count = 0
    confirmation_count = 0
    conformant_count = 0
    baseline_match_count = 0
    warning_counts: dict[str, int] = {}
    run_errors: list[str] = []
    baseline_ids: set[str] = set()

    for case in cases:
        started = time.perf_counter_ns()
        observed_total: str | None = None
        observed_currency: str | None = None
        grade = "none"
        requires_confirmation = False
        warning_codes: list[str] = []
        runtime_conformant = False
        duration_ms = 0

        try:
            result = recognize(
                case.image_path,
                currency=EXPECTED_CURRENCY,
                diagnostics=False,
                runtime_policy=runtime_policy,  # type: ignore[arg-type]
            )
            observed_total = _format_total(result.total)
            observed_currency = result.currency
            grade = result.evidence_grade
            requires_confirmation = result.requires_confirmation
            warning_codes = [warning.code for warning in result.warnings]
            runtime_conformant = result.runtime.conformant
            baseline_ids.add(result.runtime.baseline_id)
            if result.runtime.baseline_id == expected_baseline_id:
                baseline_match_count += 1
            duration_ms = result.duration_ms
        except ReceiptOcrError as error:
            warning_codes = [f"error:{error.code}"]
            run_errors.append(f"{case.case_id}: {error.code}")
            duration_ms = int((time.perf_counter_ns() - started) / 1_000_000)
        except Exception as error:
            warning_codes = ["error:unexpected"]
            run_errors.append(f"{case.case_id}: unexpected:{error.__class__.__name__}")
            duration_ms = int((time.perf_counter_ns() - started) / 1_000_000)

        exact_match = (
            observed_total == case.expected_total and observed_currency == EXPECTED_CURRENCY
        )
        if exact_match:
            exact_match_count += 1
        if grade == "strong" and not exact_match:
            false_strong_count += 1
        if requires_confirmation:
            confirmation_count += 1
        if runtime_conformant:
            conformant_count += 1
        for warning_code in warning_codes:
            warning_counts[warning_code] = warning_counts.get(warning_code, 0) + 1
        durations.append(duration_ms)
        evaluated_cases.append(
            {
                "case_id": case.case_id,
                "expected_total": case.expected_total,
                "expected_currency": case.expected_currency,
                "observed_total": observed_total,
                "observed_currency": observed_currency,
                "grade": grade,
                "requires_confirmation": requires_confirmation,
                "warning_codes": warning_codes,
                "duration_ms": duration_ms,
                "exact_match": exact_match,
            }
        )

    sorted_durations = sorted(durations)
    p95_duration_ms = _nearest_rank(sorted_durations, 0.95)
    case_count = len(cases)
    exact_rate = exact_match_count / case_count
    confirmation_rate = confirmation_count / case_count
    fully_conformant = conformant_count == case_count
    baseline_match = baseline_match_count == case_count
    eligible = (
        runtime_policy == "conformant" and fully_conformant and baseline_match and not run_errors
    )
    gates = {
        "eligible": eligible,
        "exact_amount_currency_rate_min_0_95": exact_rate >= 0.95,
        "false_strong_count_zero": false_strong_count == 0,
        "confirmation_rate_eq_1_0": confirmation_rate == 1.0,
        "p95_duration_ms_lt_5000": p95_duration_ms < 5000,
    }
    gate_passed = eligible and all(gates.values())

    summary = {
        "case_count": case_count,
        "exact_match_count": exact_match_count,
        "exact_match_rate": round(exact_rate, 6),
        "false_strong_count": false_strong_count,
        "confirmation_rate": round(confirmation_rate, 6),
        "conformant_case_count": conformant_count,
        "baseline_match_case_count": baseline_match_count,
        "p95_duration_ms": p95_duration_ms,
        "runtime_baseline_ids": sorted(baseline_ids),
        "warning_counts": dict(sorted(warning_counts.items())),
        "error_count": len(run_errors),
        "errors": run_errors,
        "gates": gates,
        "gate_passed": gate_passed,
    }
    return evaluated_cases, summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools/holdout/evaluate.py",
        description="Evaluate a private holdout corpus through public recognize().",
    )
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Path to private manifest JSON"
    )
    parser.add_argument(
        "--corpus-root", type=Path, required=True, help="Root directory of holdout images"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output path for JSON report")
    parser.add_argument(
        "--allow-development-runtime",
        action="store_true",
        help="Run with runtime_policy=development for dry runs; report stays ineligible.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    runtime_policy = "development" if args.allow_development_runtime else "conformant"

    manifest_path = args.manifest.expanduser().resolve()
    corpus_root = args.corpus_root.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    try:
        metadata, cases = load_manifest(manifest_path, corpus_root)
    except (ManifestError, OSError, json.JSONDecodeError) as error:
        print(f"holdout evaluation failed: {error}", file=sys.stderr)
        return 2

    started_at = datetime.now(timezone.utc)
    evaluated_cases, aggregates = evaluate_holdout(
        cases=cases,
        runtime_policy=runtime_policy,
        expected_baseline_id=metadata["runtime_baseline_id"],
    )
    finished_at = datetime.now(timezone.utc)
    report = {
        "tool": "payable-receipt-ocr holdout evaluator",
        "report_schema": "payable-receipt-ocr/holdout-eval/1",
        "generated_at": finished_at.isoformat(),
        "manifest": metadata,
        "run": {
            "runtime_policy": runtime_policy,
            "allow_development_runtime": args.allow_development_runtime,
            "conformant": bool(
                runtime_policy == "conformant"
                and aggregates["conformant_case_count"] == len(cases)
                and aggregates["baseline_match_case_count"] == len(cases)
            ),
            "eligible_for_gate": bool(aggregates["gates"]["eligible"]),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        },
        "cases": evaluated_cases,
        "aggregates": aggregates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if aggregates["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
