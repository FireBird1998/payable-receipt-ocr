"""Private orchestration for the receipt recognition pipeline."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal, Optional

from ._image import load_source_image, prepare_variants
from ._interpretation import interpret
from ._ocr import build_schedule, execute_schedule
from ._runtime import validate_runtime
from .errors import ConfigurationError, OcrEngineError

SUPPORTED_CURRENCIES = {"INR"}


def process_receipt(
    path: Path,
    *,
    currency_context: str,
    tessdata_dir: Optional[Path],
    pass_timeout_seconds: float,
    deadline_seconds: float,
    diagnostics: bool,
    runtime_policy: Literal["development", "conformant"],
) -> dict[str, Any]:
    started_at = time.monotonic()
    deadline_at = started_at + deadline_seconds
    if currency_context.upper() != "INR":
        raise ConfigurationError("Only INR is supported in the production runtime.")
    if pass_timeout_seconds <= 0:
        raise ConfigurationError("pass_timeout_seconds must be greater than zero.")
    if deadline_seconds <= 0:
        raise ConfigurationError("deadline_seconds must be greater than zero.")
    source = load_source_image(path)
    remaining_for_runtime = deadline_at - time.monotonic()
    if remaining_for_runtime <= 0:
        raise OcrEngineError("Recognition deadline reached during input preparation.")
    runtime = validate_runtime(
        tessdata_dir=tessdata_dir,
        runtime_policy=runtime_policy,
        timeout_seconds=min(pass_timeout_seconds, remaining_for_runtime),
    )
    variants, preprocessing = prepare_variants(source)
    variant_lookup = {variant.name: variant for variant in variants}

    baseline_schedule = build_schedule(include_adaptive=False, include_rescue=False)
    baseline_run = execute_schedule(
        variants=variant_lookup,
        planned=baseline_schedule,
        tessdata_dir=str(runtime.tessdata_dir),
        pass_timeout_seconds=pass_timeout_seconds,
        deadline_at=deadline_at,
        omp_thread_limit=runtime.omp_thread_limit,
    )
    baseline_interpretation = interpret(
        passes=baseline_run.completed,
        currency_context="INR",
        degraded=baseline_run.failed > 0 or baseline_run.deadline_exceeded,
        diagnostics=False,
    )
    should_extend = baseline_interpretation.evidence_grade != "strong"

    extended_completed = baseline_run.completed
    extended_failed = baseline_run.failed
    extended_warnings = list(baseline_run.warnings)
    deadline_exceeded = baseline_run.deadline_exceeded
    planned_total = baseline_run.planned

    if should_extend and not deadline_exceeded:
        remainder_schedule = build_schedule(include_adaptive=True, include_rescue=True)[
            len(baseline_schedule) :
        ]
        remainder_run = execute_schedule(
            variants=variant_lookup,
            planned=remainder_schedule,
            tessdata_dir=str(runtime.tessdata_dir),
            pass_timeout_seconds=pass_timeout_seconds,
            deadline_at=deadline_at,
            omp_thread_limit=runtime.omp_thread_limit,
        )
        planned_total += remainder_run.planned
        extended_completed = extended_completed + remainder_run.completed
        extended_failed += remainder_run.failed
        extended_warnings.extend(remainder_run.warnings)
        deadline_exceeded = deadline_exceeded or remainder_run.deadline_exceeded

    if not extended_completed and extended_failed > 0:
        raise OcrEngineError("All OCR passes failed.")
    if not extended_completed and deadline_exceeded:
        raise OcrEngineError("No OCR pass completed before the deadline.")

    degraded = extended_failed > 0 or deadline_exceeded
    interpretation = interpret(
        passes=extended_completed,
        currency_context="INR",
        degraded=degraded,
        diagnostics=diagnostics,
    )
    duration_ms = int((time.monotonic() - started_at) * 1000)

    warning_payload = [warning.to_dict() for warning in interpretation.warnings]
    warning_payload.extend(warning.to_dict() for warning in extended_warnings)
    unique_warnings = _dedupe_warnings(warning_payload)
    if interpretation.evidence_grade != "strong":
        unique_warnings.append(
            {
                "code": "weak_evidence",
                "message": "Independent OCR evidence did not meet the strong-suggestion gate.",
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "payable-receipt-ocr/1",
        "source": {"filename": source.filename, "dimensions": [source.width, source.height]},
        "processing": {
            "passes_planned": planned_total,
            "passes_completed": len(extended_completed),
            "passes_failed": extended_failed,
            "degraded": degraded,
            "deadline_exceeded": deadline_exceeded,
            "duration_ms": duration_ms,
            "processed_dimensions": preprocessing["processed_dimensions"],
            "deadline_seconds": deadline_seconds,
            "pass_timeout_seconds": pass_timeout_seconds,
            "max_workers": 1,
        },
        "runtime": {
            "baseline_id": runtime.baseline_id,
            "conformant": runtime.conformant,
            "tesseract_version": runtime.tesseract_version,
            "model_sha256": runtime.model_sha256,
        },
        "result": {
            "total": interpretation.total,
            "currency": interpretation.currency,
            "evidence_grade": interpretation.evidence_grade,
            "requires_confirmation": True,
            "authorizes_persistence": False,
            "matched_label": interpretation.matched_label,
            "label_kind": interpretation.label_kind,
        },
        "warnings": unique_warnings,
    }
    if diagnostics and interpretation.diagnostics is not None:
        payload["diagnostics"] = interpretation.diagnostics
    return payload


def _dedupe_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for warning in warnings:
        key = (warning["code"], warning["message"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(warning)
    return unique
