from __future__ import annotations

import math
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2

from ._contracts import OcrLine, OcrPassResult, OcrWarning, PreparedVariant


@dataclass(frozen=True)
class PlannedPass:
    variant: str
    language: str
    psm: int

    @property
    def pass_id(self) -> str:
        return f"{self.variant}:{self.language}:psm{self.psm}"


@dataclass(frozen=True)
class OcrExecutionResult:
    planned: int
    completed: tuple[OcrPassResult, ...]
    failed: int
    warnings: tuple[OcrWarning, ...]
    deadline_exceeded: bool

    @property
    def degraded(self) -> bool:
        return (
            self.failed > 0
            or self.deadline_exceeded
            or any(ocr_pass.malformed_records for ocr_pass in self.completed)
        )


def build_schedule(*, include_adaptive: bool, include_rescue: bool) -> tuple[PlannedPass, ...]:
    schedule: list[PlannedPass] = []
    base_variants = ("normalized-grayscale",)
    adaptive_variants = ("adaptive-threshold",) if include_adaptive else ()
    rescue_psm = (11,) if include_rescue else ()
    for variant in base_variants:
        for language in ("eng", "Devanagari"):
            for psm in (6, 4):
                schedule.append(PlannedPass(variant=variant, language=language, psm=psm))
    for variant in adaptive_variants:
        for language in ("eng", "Devanagari"):
            for psm in (6, 4):
                schedule.append(PlannedPass(variant=variant, language=language, psm=psm))
    for variant in ("normalized-grayscale", "adaptive-threshold"):
        if variant == "adaptive-threshold" and not include_adaptive:
            continue
        for language in ("eng", "Devanagari"):
            for psm in rescue_psm:
                schedule.append(PlannedPass(variant=variant, language=language, psm=psm))
    return tuple(schedule)


def execute_schedule(
    *,
    variants: dict[str, PreparedVariant],
    planned: tuple[PlannedPass, ...],
    tessdata_dir: str,
    pass_timeout_seconds: float,
    deadline_at: float,
    omp_thread_limit: str,
) -> OcrExecutionResult:
    completed: list[OcrPassResult] = []
    warnings: list[OcrWarning] = []
    failed = 0
    deadline_exceeded = False

    for current in planned:
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            deadline_exceeded = True
            break
        timeout_seconds = min(pass_timeout_seconds, remaining)
        try:
            ocr_pass = _run_pass(
                image=variants[current.variant].image,
                language=current.language,
                psm=current.psm,
                pass_id=current.pass_id,
                variant=current.variant,
                tessdata_dir=tessdata_dir,
                timeout_seconds=timeout_seconds,
                omp_thread_limit=omp_thread_limit,
            )
        except RuntimeError:
            failed += 1
            warnings.append(
                OcrWarning(
                    code="pass_timeout",
                    message=f"OCR pass timed out after {timeout_seconds:.2f}s",
                    pass_id=current.pass_id,
                )
            )
            continue
        except OSError as error:
            failed += 1
            warnings.append(
                OcrWarning(
                    code="pass_failed",
                    message=f"OCR pass failed: {error}",
                    pass_id=current.pass_id,
                )
            )
            continue
        completed.append(ocr_pass)
        if ocr_pass.malformed_records:
            warnings.append(
                OcrWarning(
                    code="ocr_malformed_records",
                    message=f"Discarded {ocr_pass.malformed_records} malformed OCR records.",
                    pass_id=current.pass_id,
                )
            )
    if deadline_exceeded:
        warnings.append(
            OcrWarning(
                code="deadline_exceeded",
                message="The total recognition deadline was reached",
            )
        )
    return OcrExecutionResult(
        planned=len(planned),
        completed=tuple(completed),
        failed=failed,
        warnings=tuple(warnings),
        deadline_exceeded=deadline_exceeded,
    )


def _run_pass(
    *,
    image,
    language: str,
    psm: int,
    pass_id: str,
    variant: str,
    tessdata_dir: str,
    timeout_seconds: float,
    omp_thread_limit: str,
) -> OcrPassResult:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        image_path = Path(handle.name)
    try:
        if not cv2.imwrite(str(image_path), image):
            raise OSError("Unable to create the temporary OCR input image")
        command = [
            "tesseract",
            str(image_path),
            "stdout",
            "-l",
            language,
            "--oem",
            "1",
            "--psm",
            str(psm),
            "-c",
            "preserve_interword_spaces=1",
            "-c",
            "tessedit_create_tsv=1",
            "--tessdata-dir",
            tessdata_dir,
        ]
        process_environment = dict(os.environ)
        process_environment["OMP_THREAD_LIMIT"] = omp_thread_limit
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=process_environment,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Tesseract pass timed out") from error
        except OSError as error:
            raise OSError("Unable to execute Tesseract") from error
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()
            message = detail[-1] if detail else "unknown Tesseract failure"
            raise OSError(f"Tesseract exited with status {completed.returncode}: {message}")
        words, malformed_records = _parse_tsv(completed.stdout, image.shape[:2])
    finally:
        image_path.unlink(missing_ok=True)

    rows: list[dict[str, object]] = []
    confidences = [float(word["confidence"]) for word in words]
    # Fix the processing order so TSV record order cannot change row membership.
    for word in sorted(words, key=lambda item: (item["top"], item["left"], item["text"])):
        _place_word(rows, word)
    lines: list[OcrLine] = []
    for row in sorted(rows, key=lambda item: item["top"]):
        row_words = sorted(row["words"], key=lambda item: item["left"])
        line_confidences = [float(item["confidence"]) for item in row_words]
        lines.append(
            OcrLine(
                text=" ".join(str(item["text"]) for item in row_words),
                confidence=round(sum(line_confidences) / len(line_confidences), 2),
                top=int(row["top"]),
                bottom=int(row["bottom"]),
            )
        )
    average = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return OcrPassResult(
        pass_id=pass_id,
        variant=variant,
        language=language,
        psm=psm,
        average_confidence=average,
        lines=tuple(lines),
        malformed_records=malformed_records,
    )


def _place_word(rows: list[dict[str, object]], word: dict[str, object]) -> None:
    matching_row: Optional[dict[str, object]] = None
    best_distance = float("inf")
    for row in rows:
        center_distance = abs(float(row["center"]) - float(word["center"]))
        # Compatibility with every member prevents tall boxes and transitive
        # overlap chains from expanding the row into unrelated receipt lines.
        grouped_row = all(_same_row(member, word) for member in row["words"])
        if grouped_row and center_distance < best_distance:
            matching_row = row
            best_distance = center_distance
    if matching_row is None:
        rows.append(
            {
                "words": [word],
                "top": int(word["top"]),
                "bottom": int(word["bottom"]),
                "center": float(word["center"]),
            }
        )
        return
    words = matching_row["words"]
    assert isinstance(words, list)
    words.append(word)
    matching_row["top"] = min(int(matching_row["top"]), int(word["top"]))
    matching_row["bottom"] = max(int(matching_row["bottom"]), int(word["bottom"]))
    matching_row["center"] = sum(float(item["center"]) for item in words) / len(words)


_TSV_HEADER = (
    "level",
    "page_num",
    "block_num",
    "par_num",
    "line_num",
    "word_num",
    "left",
    "top",
    "width",
    "height",
    "conf",
    "text",
)


def _parse_tsv(output: str, image_shape: tuple[int, int]) -> tuple[list[dict[str, object]], int]:
    # Tesseract emits literal tab-separated text, not CSV-escaped fields.
    # Split physical lines so an unmatched quote cannot consume later records.
    records = output.split("\n")
    if tuple(records[0].rstrip("\r").split("\t")) != _TSV_HEADER:
        raise OSError("Malformed Tesseract TSV header")
    image_height, image_width = image_shape
    words: list[dict[str, object]] = []
    malformed = 0
    for record in records[1:]:
        if not record.strip():
            continue
        fields = record.rstrip("\r").split("\t")
        try:
            if len(fields) != len(_TSV_HEADER):
                raise ValueError
            level, page, block, paragraph, line, number, left, top, width, height = (
                int(field) for field in fields[:10]
            )
            confidence = float(fields[10])
            if (
                level not in range(1, 6)
                or page < 1
                or min(block, paragraph, line, number, left, top) < 0
                or min(width, height) <= 0
                or left + width > image_width
                or top + height > image_height
                or not math.isfinite(confidence)
            ):
                raise ValueError
            if level != 5:
                if fields[11].strip() or confidence != -1:
                    raise ValueError
                continue
            if not 0 <= confidence <= 100:
                raise ValueError
        except ValueError:
            malformed += 1
            continue
        text = fields[11].strip()
        if text:
            words.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "left": left,
                    "top": top,
                    "bottom": top + height,
                    "center": top + height / 2.0,
                }
            )
    return words, malformed


def _same_row(first: dict[str, object], second: dict[str, object]) -> bool:
    first_height = int(first["bottom"]) - int(first["top"])
    second_height = int(second["bottom"]) - int(second["top"])
    min_height = min(first_height, second_height)
    max_height = max(first_height, second_height)
    overlap = min(int(first["bottom"]), int(second["bottom"])) - max(
        int(first["top"]), int(second["top"])
    )
    center_distance = abs(float(first["center"]) - float(second["center"]))
    return (
        max_height <= 2.5 * min_height
        and overlap >= 0.35 * min_height
        and center_distance <= 0.65 * min_height
    )
