#!/usr/bin/env python3
"""Local receipt image -> corroborated payment-total suggestion.

This module contains the v4 recognition implementation. Callers should use
``payable_receipt_ocr.recognize`` instead of importing this module directly.
"""

import argparse
import base64
import html
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from pytesseract import Output

from .errors import ConfigurationError, OcrEngineError, UnsupportedImageError

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_CURRENCIES = {"INR", "USD", "EUR", "GBP", "UNKNOWN"}
PSM_MODES = (4, 6, 11)

CURRENCY_PATTERN = r"(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)"
NUMBER_PATTERN = (
    r"(?:\d{1,2}(?:,\d{2})+(?:,\d{3})?|\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d{1,2})?"
)
MONEY_PATTERN = re.compile(
    r"(?<!\d)(?P<prefix>{})?\s*(?P<amount>{})\s*"
    r"(?P<suffix>INR|USD|EUR|GBP)?(?!\d)".format(CURRENCY_PATTERN, NUMBER_PATTERN),
    re.IGNORECASE,
)
CURRENCY_TOKEN_PATTERNS = (
    (re.compile(r"₹"), "INR"),
    (re.compile(r"(?<![A-Za-z0-9])Rs\.?(?![A-Za-z])", re.IGNORECASE), "INR"),
    (re.compile(r"(?<![A-Za-z0-9])INR(?![A-Za-z0-9])", re.IGNORECASE), "INR"),
    (re.compile(r"\$"), "USD"),
    (re.compile(r"(?<![A-Za-z0-9])USD(?![A-Za-z0-9])", re.IGNORECASE), "USD"),
    (re.compile(r"€"), "EUR"),
    (re.compile(r"(?<![A-Za-z0-9])EUR(?![A-Za-z0-9])", re.IGNORECASE), "EUR"),
    (re.compile(r"£"), "GBP"),
    (re.compile(r"(?<![A-Za-z0-9])GBP(?![A-Za-z0-9])", re.IGNORECASE), "GBP"),
)

PAYMENT_LABELS = (
    ("amount paid", 180),
    ("paid by you", 178),
    ("amount payable", 172),
    ("net payable", 170),
    ("to pay", 168),
    ("amount due", 165),
    ("total due", 162),
    ("balance due", 160),
    ("grand total", 155),
    ("order total", 150),
    ("bill total", 148),
    ("total bill", 145),
    ("net amount", 140),
)
FALLBACK_TOTAL_LABELS = (
    ("total bill amount", 112),
    ("item total & gst", 108),
    ("mrp total", 90),
)
NEGATIVE_TOTAL_LABELS = (
    "total savings",
    "total saving",
    "total discount",
)
COMPONENT_LABELS = (
    ("item total", "addition"),
    ("items total", "addition"),
    ("item cost", "addition"),
    ("subtotal", "addition"),
    ("sub total", "addition"),
    ("delivery fee", "addition"),
    ("delivery charge", "addition"),
    ("handling fee", "addition"),
    ("handling charge", "addition"),
    ("handling cost", "addition"),
    ("surge charge", "addition"),
    ("taxes and charges", "addition"),
    ("tax and charges", "addition"),
    ("platform fee", "addition"),
    ("processing fee", "addition"),
    ("service charge", "addition"),
    ("gst", "addition"),
    ("tax", "addition"),
    ("discount", "subtraction"),
    ("promo", "subtraction"),
    ("coupon", "subtraction"),
    ("wallet", "subtraction"),
    ("cashback", "subtraction"),
    ("saving", "ignore"),
    ("tip", "ignore"),
    ("cash", "ignore"),
    ("change", "ignore"),
    ("tendered", "ignore"),
    ("paid", "ignore"),
)


@dataclass
class OcrLine:
    text: str
    confidence: float
    top: int
    bottom: int


@dataclass
class OcrPass:
    pass_id: str
    variant: str
    language: str
    psm: int
    average_confidence: float
    lines: List[OcrLine]


@dataclass
class MoneyCandidate:
    amount: str
    currency: str
    explicit_currency: bool
    token: str
    line: str
    normalized_line: str
    line_index: int
    label: Optional[str]
    label_kind: str
    component_role: Optional[str]
    ocr_confidence: float
    pass_id: str
    variant: str
    language: str
    psm: int
    score: float
    reasons: List[str]


def _require_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise OcrEngineError(
            "Tesseract is not installed or not on PATH. See the installation guide in README.md."
        )


def _model_directory(explicit: Optional[Path] = None) -> Optional[Path]:
    candidates: List[Path] = []
    if explicit:
        candidates.append(explicit.expanduser())
    environment = os.environ.get("PAYABLE_RECEIPT_OCR_TESSDATA_DIR")
    if environment:
        candidates.append(Path(environment).expanduser())
    candidates.append(Path(__file__).resolve().parent / ".models" / "tessdata_fast")

    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "Devanagari.traineddata").is_file():
            return resolved
    return None


def _load_image(path: Path) -> Tuple[np.ndarray, Tuple[int, int]]:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise UnsupportedImageError(
            "Unsupported image type: {}. Use JPG, JPEG, PNG, or WebP.".format(
                path.suffix or "no extension"
            )
        )
    with Image.open(path) as opened:
        rgb = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = rgb.size
        if width * height > 30_000_000:
            raise UnsupportedImageError("Image exceeds the 30 megapixel limit")
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR), rgb.size


def _deskew(image: np.ndarray) -> Tuple[np.ndarray, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    height, width = image.shape[:2]
    detected_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 1800,
        threshold=80,
        minLineLength=max(60, int(width * 0.15)),
        maxLineGap=25,
    )
    if detected_lines is None:
        return image, 0.0

    angles = []
    for detected_line in detected_lines:
        x1, y1, x2, y2 = detected_line[0]
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if -12 <= angle <= 12:
            angles.append(angle)
    if not angles:
        return image, 0.0

    angle = float(np.median(angles))
    if abs(angle) < 0.15 or abs(angle) > 12:
        return image, 0.0

    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, round(angle, 3)


def _preprocess(image: np.ndarray) -> Tuple[List[Tuple[str, np.ndarray]], Dict[str, Any]]:
    deskewed, angle = _deskew(image)
    _height, width = deskewed.shape[:2]
    scale = max(1.0, min(2.5, 1800.0 / float(width)))
    if scale > 1.01:
        deskewed = cv2.resize(
            deskewed,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    gray = cv2.cvtColor(deskewed, cv2.COLOR_BGR2GRAY)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    thresholded = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        13,
    )
    variants = [
        (
            "normalized-grayscale",
            cv2.copyMakeBorder(gray, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=255),
        ),
        (
            "adaptive-threshold",
            cv2.copyMakeBorder(thresholded, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=255),
        ),
    ]
    return variants, {
        "deskew_angle_degrees": angle,
        "scale_factor": round(scale, 3),
        "processed_dimensions": [int(deskewed.shape[1]), int(deskewed.shape[0])],
    }


def _ocr_lines(
    image: np.ndarray,
    language: str,
    psm: int,
    tessdata_dir: Optional[Path],
    timeout_seconds: float,
) -> Tuple[List[OcrLine], float]:
    config_parts = [
        "--oem 1",
        "--psm {}".format(psm),
        "-c preserve_interword_spaces=1",
    ]
    if tessdata_dir is not None:
        config_parts.append('--tessdata-dir "{}"'.format(tessdata_dir))
    try:
        data = pytesseract.image_to_data(
            image,
            lang=language,
            config=" ".join(config_parts),
            output_type=Output.DICT,
            timeout=timeout_seconds,
        )
    except RuntimeError as error:
        raise OcrEngineError(
            "Tesseract pass timed out after {:.1f}s for language={} psm={}".format(
                timeout_seconds, language, psm
            )
        ) from error
    words: List[Dict[str, Any]] = []
    confidences: List[float] = []

    for index, raw_text in enumerate(data["text"]):
        word = raw_text.strip()
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        if not word or confidence < 0:
            continue

        top = int(data["top"][index])
        height = int(data["height"][index])
        words.append(
            {
                "text": word,
                "confidence": confidence,
                "left": int(data["left"][index]),
                "top": top,
                "bottom": top + height,
                "center": top + (height / 2.0),
            }
        )
        confidences.append(confidence)

    # Tesseract often assigns a label and its right-aligned amount to different
    # internal blocks. Rebuild visual rows from word geometry before parsing.
    rows: List[Dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item["center"], item["left"])):
        matching_row: Optional[Dict[str, Any]] = None
        best_distance = float("inf")
        for row in rows:
            overlap = min(row["bottom"], word["bottom"]) - max(row["top"], word["top"])
            minimum_height = max(1, min(row["bottom"] - row["top"], word["bottom"] - word["top"]))
            center_distance = abs(row["center"] - word["center"])
            overlaps = overlap >= minimum_height * 0.35
            nearby = center_distance <= max(10.0, minimum_height * 0.55)
            if (overlaps or nearby) and center_distance < best_distance:
                matching_row = row
                best_distance = center_distance
        if matching_row is None:
            rows.append(
                {
                    "words": [word],
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "center": word["center"],
                }
            )
            continue
        matching_row["words"].append(word)
        matching_row["top"] = min(matching_row["top"], word["top"])
        matching_row["bottom"] = max(matching_row["bottom"], word["bottom"])
        matching_row["center"] = sum(item["center"] for item in matching_row["words"]) / len(
            matching_row["words"]
        )

    lines = []
    for row in sorted(rows, key=lambda item: item["top"]):
        row_words = sorted(row["words"], key=lambda item: item["left"])
        line_confidences = [item["confidence"] for item in row_words]
        lines.append(
            OcrLine(
                text=" ".join(item["text"] for item in row_words),
                confidence=round(sum(line_confidences) / len(line_confidences), 2),
                top=row["top"],
                bottom=row["bottom"],
            )
        )

    average = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return lines, average


def _normalized_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    output: List[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if category in {"Mn", "Cf"}:
            continue
        try:
            output.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            output.append(character)
    return re.sub(r"\s+", " ", "".join(output)).strip()


def _classify_line(text: str) -> Tuple[str, Optional[str], Optional[str], int]:
    lowered = _normalized_search_text(text).lower()
    for label in NEGATIVE_TOTAL_LABELS:
        if label in lowered:
            return "component", label, "ignore", -90

    # These phrases describe a useful fallback total, but not necessarily the
    # amount ultimately charged after fees, discounts, or wallet adjustments.
    # Match them before shorter payment labels such as "total bill".
    for label, points in FALLBACK_TOTAL_LABELS:
        if label in lowered:
            return "fallback", label, None, points

    for label, points in PAYMENT_LABELS:
        if label in lowered:
            return "payment", label, None, points

    if re.search(r"\btotal\b", lowered) and not re.search(
        r"\b(?:sub\s*total|item[s]? total)\b", lowered
    ):
        return "fallback", "total", None, 95

    for label, role in COMPONENT_LABELS:
        if label in lowered:
            return "component", label, role, -70 if role == "ignore" else -45
    return "unlabeled", None, None, 0


def _currency_from_marker(marker: Optional[str]) -> Optional[str]:
    if not marker:
        return None
    compact = marker.strip().upper()
    if compact in {"₹", "RS", "RS.", "INR"}:
        return "INR"
    if compact in {"$", "USD"}:
        return "USD"
    if compact in {"€", "EUR"}:
        return "EUR"
    if compact in {"£", "GBP"}:
        return "GBP"
    return None


def _document_currency(lines: Sequence[OcrLine]) -> str:
    votes: Counter[str] = Counter()
    for line in lines:
        normalized = _normalized_search_text(line.text)
        for pattern, currency in CURRENCY_TOKEN_PATTERNS:
            votes[currency] += len(pattern.findall(normalized))
    return votes.most_common(1)[0][0] if votes else "UNKNOWN"


def _parse_amount(token: str) -> Decimal:
    compact = token.replace(" ", "").replace(",", "")
    try:
        return Decimal(compact).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ValueError("Invalid amount token: {}".format(token)) from error


def _format_decimal(amount: Decimal) -> str:
    return format(amount.quantize(Decimal("0.01")), "f")


def _candidates_for_pass(
    ocr_pass: OcrPass, image_height: int, currency_context: str
) -> List[MoneyCandidate]:
    fallback_currency = _document_currency(ocr_pass.lines)
    found: List[MoneyCandidate] = []

    for line_index, line in enumerate(ocr_pass.lines):
        searchable = _normalized_search_text(line.text)
        label_kind, label, component_role, label_points = _classify_line(searchable)
        matches = list(MONEY_PATTERN.finditer(searchable))
        for match_index, match in enumerate(matches):
            prefix_currency = _currency_from_marker(match.group("prefix"))
            suffix_currency = _currency_from_marker(match.group("suffix"))
            explicit_currency = prefix_currency or suffix_currency
            amount_token = match.group("amount")

            if label_kind == "unlabeled" and not explicit_currency and "." not in amount_token:
                continue
            if match.end() < len(searchable) and searchable[match.end() :].lstrip().startswith("%"):
                continue

            reasons: List[str] = []
            score = float(label_points)
            if label:
                reasons.append("{} {} label {:+d}".format(label_kind, label, label_points))

            vertical_ratio = min(1.0, max(0.0, line.bottom / float(max(1, image_height))))
            position_points = round(vertical_ratio * 14, 2)
            score += position_points
            reasons.append("page position +{:.2f}".format(position_points))

            confidence_points = round(max(0.0, line.confidence) / 10.0, 2)
            score += confidence_points
            reasons.append("OCR confidence +{:.2f}".format(confidence_points))

            if match_index == len(matches) - 1:
                score += 8
                reasons.append("rightmost amount +8")

            if explicit_currency:
                score += 7
                reasons.append("explicit {} marker +7".format(explicit_currency))
                if currency_context != "UNKNOWN" and explicit_currency == currency_context:
                    score += 5
                    reasons.append("currency context agreement +5")
                elif currency_context != "UNKNOWN" and explicit_currency != currency_context:
                    score -= 9
                    reasons.append("currency context conflict -9")

            currency = explicit_currency or fallback_currency
            if currency == "UNKNOWN" and currency_context != "UNKNOWN":
                currency = currency_context
                reasons.append("currency supplied by expense context")

            found.append(
                MoneyCandidate(
                    amount=_format_decimal(_parse_amount(amount_token)),
                    currency=currency,
                    explicit_currency=explicit_currency is not None,
                    token=match.group(0).strip(),
                    line=line.text,
                    normalized_line=searchable,
                    line_index=line_index,
                    label=label,
                    label_kind=label_kind,
                    component_role=component_role,
                    ocr_confidence=line.confidence,
                    pass_id=ocr_pass.pass_id,
                    variant=ocr_pass.variant,
                    language=ocr_pass.language,
                    psm=ocr_pass.psm,
                    score=round(score, 2),
                    reasons=reasons,
                )
            )

    return sorted(found, key=lambda candidate: candidate.score, reverse=True)


def _arithmetic_matches(candidates: Sequence[MoneyCandidate]) -> Dict[str, List[str]]:
    by_pass: Dict[str, List[MoneyCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_pass[candidate.pass_id].append(candidate)

    matches: Dict[str, List[str]] = defaultdict(list)
    for pass_id, pass_candidates in by_pass.items():
        finals = [
            candidate
            for candidate in pass_candidates
            if candidate.label_kind in {"payment", "fallback"}
        ]
        if not finals:
            continue
        final = max(finals, key=lambda candidate: (candidate.score, candidate.line_index))

        component_by_line: Dict[int, MoneyCandidate] = {}
        for candidate in pass_candidates:
            if candidate.label_kind != "component" or candidate.component_role not in {
                "addition",
                "subtraction",
            }:
                continue
            current = component_by_line.get(candidate.line_index)
            if current is None or candidate.token == candidate.normalized_line.split()[-1]:
                component_by_line[candidate.line_index] = candidate
            elif candidate.line_index == current.line_index:
                component_by_line[candidate.line_index] = candidate

        components = list(component_by_line.values())
        if len(components) < 2:
            continue
        calculated = Decimal("0")
        for component in components:
            signed = Decimal(component.amount)
            calculated += -signed if component.component_role == "subtraction" else signed
        displayed = Decimal(final.amount)
        tolerance = max(Decimal("0.50"), displayed * Decimal("0.005"))
        if abs(calculated - displayed) <= tolerance:
            matches[final.amount].append(pass_id)
    return matches


def _aggregate_candidates(
    candidates: Sequence[MoneyCandidate],
    currency_context: str,
) -> List[Dict[str, Any]]:
    arithmetic = _arithmetic_matches(candidates)
    grouped: Dict[str, List[MoneyCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.label_kind in {"payment", "fallback"}:
            grouped[candidate.amount].append(candidate)

    groups: List[Dict[str, Any]] = []
    for amount, amount_candidates in grouped.items():
        pass_ids = sorted({candidate.pass_id for candidate in amount_candidates})
        languages = sorted({candidate.language for candidate in amount_candidates})
        variants = sorted({candidate.variant for candidate in amount_candidates})
        psm_modes = sorted({candidate.psm for candidate in amount_candidates})
        explicit_votes = Counter(
            candidate.currency for candidate in amount_candidates if candidate.explicit_currency
        )
        currency = currency_context
        if currency == "UNKNOWN":
            currency = explicit_votes.most_common(1)[0][0] if explicit_votes else "UNKNOWN"

        best = max(
            amount_candidates,
            key=lambda candidate: (
                candidate.label_kind == "payment",
                candidate.currency == currency,
                candidate.explicit_currency,
                candidate.score,
                candidate.ocr_confidence,
            ),
        )
        arithmetic_pass_ids = sorted(set(arithmetic.get(amount, [])))
        matching_currency_votes = (
            explicit_votes.get(currency_context, 0) if currency_context != "UNKNOWN" else 0
        )
        conflicting_currency_votes = (
            sum(explicit_votes.values()) - matching_currency_votes
            if currency_context != "UNKNOWN"
            else 0
        )
        aggregate_score = (
            max(candidate.score for candidate in amount_candidates)
            + min(36, len(pass_ids) * 5)
            + max(0, len(languages) - 1) * 14
            + max(0, len(variants) - 1) * 5
            + min(12, len(arithmetic_pass_ids) * 4)
            + min(8, matching_currency_votes * 2)
            - min(4, conflicting_currency_votes)
        )
        groups.append(
            {
                "amount": amount,
                "currency": currency,
                "score": round(aggregate_score, 2),
                "support_count": len(pass_ids),
                "pass_ids": pass_ids,
                "languages": languages,
                "variants": variants,
                "psm_modes": psm_modes,
                "explicit_currency_votes": dict(explicit_votes),
                "matching_currency_votes": matching_currency_votes,
                "conflicting_currency_votes": conflicting_currency_votes,
                "arithmetic_pass_ids": arithmetic_pass_ids,
                "matched_label": best.label,
                "label_kind": best.label_kind,
                "matched_line": best.line,
                "normalized_line": best.normalized_line,
                "representative_pass_id": best.pass_id,
                "candidate_count": len(amount_candidates),
                "ranking_warnings": [],
            }
        )

    # Tesseract's Devanagari pass can occasionally turn the rupee glyph into a
    # leading 2 or 3 (for example, ₹356 -> 2356). When an equally strong shorter
    # candidate has the same trailing digits, treat the longer value as suspect.
    for longer in groups:
        longer_decimal = Decimal(longer["amount"])
        if longer_decimal != longer_decimal.to_integral_value():
            continue
        longer_digits = str(int(longer_decimal))
        for shorter in groups:
            if longer is shorter or longer["matched_label"] != shorter["matched_label"]:
                continue
            shorter_decimal = Decimal(shorter["amount"])
            if shorter_decimal != shorter_decimal.to_integral_value():
                continue
            shorter_digits = str(int(shorter_decimal))
            if (
                len(longer_digits) == len(shorter_digits) + 1
                and len(shorter_digits) >= 3
                and longer_digits.endswith(shorter_digits)
                and shorter["support_count"] >= longer["support_count"]
            ):
                longer["score"] = round(longer["score"] - 20, 2)
                warning = "possible leading-digit OCR corruption versus {}".format(
                    shorter["amount"]
                )
                longer["ranking_warnings"].append(warning)
                shorter["ranking_warnings"].append(
                    "competing candidate may contain a spurious leading digit"
                )
                break

    return sorted(groups, key=lambda group: (group["score"], group["support_count"]), reverse=True)


def _evidence_grade(groups: Sequence[Dict[str, Any]], currency_context: str) -> str:
    if not groups:
        return "none"
    winner = groups[0]
    language_agreement = len(winner["languages"]) >= 2
    repeated_support = winner["support_count"] >= 3
    arithmetic_agreement = len(winner["arithmetic_pass_ids"]) >= 2
    currency_supported = currency_context != "UNKNOWN" or bool(winner["explicit_currency_votes"])
    runner_safe = len(groups) == 1
    if len(groups) > 1:
        runner = groups[1]
        score_gap = winner["score"] - runner["score"]
        if runner["label_kind"] == "payment":
            runner_safe = score_gap >= 18 and winner["support_count"] >= runner["support_count"]
        else:
            runner_safe = score_gap >= 20
    if (
        winner["label_kind"] == "payment"
        and not winner["ranking_warnings"]
        and currency_supported
        and runner_safe
        and ((language_agreement and repeated_support) or arithmetic_agreement)
    ):
        return "strong"
    return "review"


def _warnings(
    groups: Sequence[Dict[str, Any]],
    grade: str,
    currency_context: str,
    has_devanagari: bool,
) -> List[str]:
    warnings: List[str] = []
    if not has_devanagari:
        warnings.append("The Devanagari OCR model was unavailable; INR evidence is weaker")
    if not groups:
        warnings.append(
            "No payment or fallback total label with a monetary value could be extracted"
        )
    if grade != "strong":
        warnings.append("Independent OCR evidence did not meet the strong-suggestion gate")
    if groups:
        winner = groups[0]
        conflicting = {
            currency
            for currency in winner["explicit_currency_votes"]
            if currency_context != "UNKNOWN" and currency != currency_context
        }
        if conflicting:
            warnings.append(
                "OCR produced conflicting currency marker(s): {}".format(
                    ", ".join(sorted(conflicting))
                )
            )
        if len(groups) > 1 and groups[1]["support_count"] >= winner["support_count"]:
            warnings.append("A competing total has equal or greater OCR-pass support")
        warnings.extend(winner["ranking_warnings"])
    return warnings


def process_receipt(
    path: Path,
    currency_context: str = "UNKNOWN",
    tessdata_dir: Optional[Path] = None,
    pass_timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    _require_tesseract()
    currency_context = currency_context.upper()
    if currency_context not in SUPPORTED_CURRENCIES:
        raise ConfigurationError("Unsupported currency context: {}".format(currency_context))
    if pass_timeout_seconds <= 0:
        raise ConfigurationError("pass_timeout_seconds must be greater than zero")

    image, original_size = _load_image(path)
    variants, processing = _preprocess(image)
    model_directory = _model_directory(tessdata_dir)
    language_configs: List[Tuple[str, Optional[Path]]] = [("eng", None)]
    if model_directory is not None:
        language_configs.append(("Devanagari", model_directory))

    ocr_passes: List[OcrPass] = []
    all_candidates: List[MoneyCandidate] = []
    for variant_name, variant_image in variants:
        for language, language_tessdata_dir in language_configs:
            for psm in PSM_MODES:
                pass_id = "{}:{}:psm{}".format(variant_name, language, psm)
                lines, average_confidence = _ocr_lines(
                    variant_image,
                    language=language,
                    psm=psm,
                    tessdata_dir=language_tessdata_dir,
                    timeout_seconds=pass_timeout_seconds,
                )
                ocr_pass = OcrPass(
                    pass_id=pass_id,
                    variant=variant_name,
                    language=language,
                    psm=psm,
                    average_confidence=average_confidence,
                    lines=lines,
                )
                ocr_passes.append(ocr_pass)
                all_candidates.extend(
                    _candidates_for_pass(ocr_pass, variant_image.shape[0], currency_context)
                )

    candidate_groups = _aggregate_candidates(all_candidates, currency_context)
    grade = _evidence_grade(candidate_groups, currency_context)
    winner = candidate_groups[0] if candidate_groups else None
    warnings = _warnings(
        candidate_groups,
        grade,
        currency_context,
        has_devanagari=model_directory is not None,
    )

    return {
        "schema_version": "payable-receipt-ocr/v1",
        "alpha": True,
        "source": {
            "filename": path.name,
            "dimensions": [original_size[0], original_size[1]],
        },
        "processing": {
            **processing,
            "currency_context": currency_context,
            "pass_timeout_seconds": pass_timeout_seconds,
            "model_directory": str(model_directory) if model_directory else None,
            "pass_count": len(ocr_passes),
            "languages": [language for language, _directory in language_configs],
            "psm_modes": list(PSM_MODES),
            "variants": [name for name, _image in variants],
        },
        "result": {
            "total": winner["amount"] if winner else None,
            "currency": winner["currency"] if winner else currency_context,
            "evidence_grade": grade,
            "requires_confirmation": True,
            "needs_review": grade != "strong",
            "matched_label": winner["matched_label"] if winner else None,
            "matched_line": winner["matched_line"] if winner else None,
        },
        "candidate_groups": candidate_groups,
        "candidates": [asdict(candidate) for candidate in all_candidates],
        "ocr": {
            "passes": [
                {
                    "pass_id": ocr_pass.pass_id,
                    "variant": ocr_pass.variant,
                    "language": ocr_pass.language,
                    "psm": ocr_pass.psm,
                    "average_confidence": ocr_pass.average_confidence,
                    "raw_text": "\n".join(line.text for line in ocr_pass.lines),
                    "lines": [asdict(line) for line in ocr_pass.lines],
                }
                for ocr_pass in ocr_passes
            ]
        },
        "warnings": warnings,
    }


def _mime_type(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def write_html_report(result: Dict[str, Any], image_path: Path, destination: Path) -> None:
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    pretty_json = html.escape(json.dumps(result, indent=2, ensure_ascii=False))
    selected = result["result"]
    groups = result["candidate_groups"]
    warnings = result["warnings"]
    pass_summaries = result["ocr"]["passes"]

    group_rows = (
        "".join(
            "<tr><td>{}</td><td>{} {}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                index + 1,
                html.escape(group["currency"]),
                html.escape(group["amount"]),
                group["support_count"],
                html.escape(", ".join(group["languages"])),
                html.escape(", ".join(group["variants"])),
                html.escape(group["matched_line"]),
            )
            for index, group in enumerate(groups)
        )
        or '<tr><td colspan="7">No payment-total candidates found</td></tr>'
    )
    pass_cards = "".join(
        '<article class="card pass-card"><div class="pass-head"><h3>{}</h3>'
        "<span>{:.1f}% OCR</span></div><pre>{}</pre></article>".format(
            html.escape(ocr_pass["pass_id"]),
            ocr_pass["average_confidence"],
            html.escape(ocr_pass["raw_text"]),
        )
        for ocr_pass in pass_summaries
    )
    warning_markup = "".join("<li>{}</li>".format(html.escape(item)) for item in warnings)
    if not warning_markup:
        warning_markup = "<li>No extraction warnings</li>"

    document = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="data:," />
  <title>Receipt OCR prototype v4 report</title>
  <style>
    :root { color-scheme:light dark; --bg:#f7f8fc; --panel:#fff; --text:#172033; --muted:#667085; --line:#dfe3ee; --brand:#4f46e5; --mint:#0f9f75; --coral:#e85d5d; }
    @media (prefers-color-scheme:dark) { :root { --bg:#111424; --panel:#1a1f33; --text:#f2f4ff; --muted:#aab2ca; --line:#343b55; --brand:#8b83ff; --mint:#56d6ad; --coral:#ff8c87; } }
    * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:15px/1.55 system-ui,-apple-system,sans-serif; }
    main { max-width:1240px; margin:0 auto; padding:32px 20px 80px; } h1,h2,h3 { margin:0; } h1 { font-size:clamp(28px,4vw,44px); letter-spacing:-.04em; }
    .eyebrow { color:var(--brand); font-weight:800; letter-spacing:.12em; text-transform:uppercase; font-size:12px; }
    .lede,.muted { color:var(--muted); } .lede { max-width:850px; } .tabs { display:flex; flex-wrap:wrap; gap:8px; margin:24px 0; }
    button { border:1px solid var(--line); background:var(--panel); color:var(--text); border-radius:999px; padding:10px 15px; cursor:pointer; font-weight:700; }
    button[aria-selected="true"] { background:var(--brand); border-color:var(--brand); color:white; }
    .panel { display:none; } .panel.active { display:block; } .grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(320px,.9fr); gap:22px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:18px; padding:20px; box-shadow:0 12px 35px rgba(35,42,70,.08); }
    .receipt { width:100%; max-height:720px; object-fit:contain; border-radius:12px; background:white; }
    .amount { font:700 clamp(36px,7vw,70px)/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--mint); margin:18px 0 8px; }
    .warning { color:var(--coral); font-weight:800; } .ok { color:var(--mint); font-weight:800; }
    pre { overflow:auto; padding:18px; border-radius:12px; background:var(--bg); border:1px solid var(--line); white-space:pre-wrap; }
    table { width:100%; border-collapse:collapse; } th,td { text-align:left; padding:12px 10px; border-bottom:1px solid var(--line); vertical-align:top; } th { color:var(--muted); font-size:12px; text-transform:uppercase; }
    .metrics { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:18px 0; } .metric { padding:14px; border:1px solid var(--line); border-radius:12px; } .metric strong { display:block; font-size:22px; }
    .pass-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; } .pass-card pre { max-height:280px; } .pass-head { display:flex; justify-content:space-between; gap:12px; align-items:center; }
    @media (max-width:800px) { .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body><main>
  <p class="eyebrow">Prototype v4 · payment-aware local OCR · no cloud calls</p>
  <h1>Can independent OCR passes agree on the bill total?</h1>
  <p class="lede">This throwaway prototype tests Blinkit, Swiggy, and Zepto-style screenshots. It keeps English and Devanagari evidence separate, exposes every pass, and always requires user confirmation.</p>
  <nav class="tabs" aria-label="Report sections">
    <button data-tab="summary" aria-selected="true">Decision</button>
    <button data-tab="agreement" aria-selected="false">Candidate agreement</button>
    <button data-tab="passes" aria-selected="false">All OCR passes</button>
    <button data-tab="pipeline" aria-selected="false">Full state</button>
  </nav>
  <section id="summary" class="panel active"><div class="grid">
    <article class="card"><img class="receipt" alt="Receipt input" src="data:__MIME__;base64,__IMAGE__" /></article>
    <article class="card"><p class="eyebrow">Suggested total</p><div class="amount">__CURRENCY__ __TOTAL__</div><p class="__STATUS_CLASS__">Evidence: __GRADE__ · confirmation always required</p><p class="muted">Matched label: __LABEL__</p><p class="muted">Matched line: __MATCHED_LINE__</p><div class="metrics"><div class="metric"><span class="muted">OCR passes</span><strong>__PASS_COUNT__</strong></div><div class="metric"><span class="muted">Supporting passes</span><strong>__SUPPORT_COUNT__</strong></div></div><h3>Warnings</h3><ul>__WARNINGS__</ul></article>
  </div></section>
  <section id="agreement" class="panel"><article class="card"><h2>Corroborated payment-total candidates</h2><p class="muted">Amounts are grouped across independent language, layout, and preprocessing passes, with final-payment labels ranked above intermediate totals.</p><div style="overflow:auto"><table><thead><tr><th>Rank</th><th>Amount</th><th>Passes</th><th>Languages</th><th>Variants</th><th>Representative line</th></tr></thead><tbody>__GROUP_ROWS__</tbody></table></div></article></section>
  <section id="passes" class="panel"><div class="pass-grid">__PASS_CARDS__</div></section>
  <section id="pipeline" class="panel"><article class="card"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><h2>Full prototype state</h2><button id="copy">Copy JSON</button></div><pre>__JSON__</pre></article></section>
</main><script>
  const state = __PAYLOAD__;
  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-tab]').forEach(item => item.setAttribute('aria-selected', String(item === button)));
    document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('active', panel.id === button.dataset.tab));
  }));
  document.getElementById('copy').addEventListener('click', async event => {
    await navigator.clipboard.writeText(JSON.stringify(state, null, 2)); event.currentTarget.textContent = 'Copied';
  });
</script></body></html>"""

    winner = groups[0] if groups else None
    replacements = {
        "__MIME__": _mime_type(image_path),
        "__IMAGE__": encoded_image,
        "__CURRENCY__": html.escape(str(selected["currency"])),
        "__TOTAL__": html.escape(str(selected["total"] or "—")),
        "__GRADE__": html.escape(str(selected["evidence_grade"]).upper()),
        "__STATUS_CLASS__": "ok" if selected["evidence_grade"] == "strong" else "warning",
        "__LABEL__": html.escape(str(selected["matched_label"] or "None")),
        "__MATCHED_LINE__": html.escape(str(selected["matched_line"] or "None")),
        "__PASS_COUNT__": str(result["processing"]["pass_count"]),
        "__SUPPORT_COUNT__": str(winner["support_count"] if winner else 0),
        "__WARNINGS__": warning_markup,
        "__GROUP_ROWS__": group_rows,
        "__PASS_CARDS__": pass_cards,
        "__JSON__": pretty_json,
        "__PAYLOAD__": payload,
    }
    for marker, value in replacements.items():
        document = document.replace(marker, value)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")


def _write_json(result: Dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="JPG, PNG, or WebP receipt image")
    parser.add_argument(
        "--currency-context",
        default="UNKNOWN",
        choices=sorted(SUPPORTED_CURRENCIES),
        help="Expense/group ISO currency used as supporting context",
    )
    parser.add_argument(
        "--tessdata-dir", type=Path, help="Directory containing Devanagari.traineddata"
    )
    parser.add_argument(
        "--pass-timeout",
        type=float,
        default=15.0,
        help="Maximum seconds for each individual Tesseract pass",
    )
    parser.add_argument("--json-out", type=Path, help="Optional structured JSON output path")
    parser.add_argument("--html-out", type=Path, help="Optional self-contained HTML report path")
    args = parser.parse_args(argv)

    try:
        image_path = args.image.expanduser().resolve(strict=True)
        result = process_receipt(
            image_path,
            currency_context=args.currency_context,
            tessdata_dir=args.tessdata_dir,
            pass_timeout_seconds=args.pass_timeout,
        )
        if args.json_out:
            _write_json(result, args.json_out)
        if args.html_out:
            write_html_report(result, image_path, args.html_out)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as error:  # Prototype CLI: one concise failure surface.
        print("payable-receipt-ocr: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
