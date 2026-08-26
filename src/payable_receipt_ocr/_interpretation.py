from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from typing import Optional

from ._contracts import (
    Candidate,
    CandidateGroup,
    InterpretationResult,
    OcrLine,
    OcrPassResult,
    OcrWarning,
)

CURRENCY_PATTERN = r"(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)"
NUMBER_PATTERN = r"(?:\d{1,2}(?:,\d{2})+(?:,\d{3})?|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
MONEY_PATTERN = re.compile(
    rf"(?<!\d)(?P<prefix>{CURRENCY_PATTERN})?\s*(?P<amount>{NUMBER_PATTERN})\s*"
    r"(?P<suffix>INR|USD|EUR|GBP)?(?!\d)",
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
NEGATIVE_TOTAL_LABELS = ("total savings", "total saving", "total discount")
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


def interpret(
    *,
    passes: tuple[OcrPassResult, ...],
    currency_context: str,
    degraded: bool,
    diagnostics: bool,
) -> InterpretationResult:
    candidates: list[Candidate] = []
    for ocr_pass in passes:
        image_height = max((line.bottom for line in ocr_pass.lines), default=1)
        candidates.extend(_candidates_for_pass(ocr_pass, image_height, currency_context))
    groups = _aggregate_candidates(tuple(candidates), currency_context)
    warnings = _rank_warnings(groups, currency_context, degraded)
    grade = _evidence_grade(groups, warnings, degraded)
    winner = groups[0] if groups else None
    if grade == "none":
        total = None
        currency = None
    else:
        total = winner.amount if winner else None
        currency = winner.currency if winner else "INR"
    diagnostics_payload = None
    if diagnostics:
        diagnostics_payload = {
            "candidate_groups": [
                {
                    "amount": group.amount,
                    "currency": group.currency,
                    "score": group.score,
                    "support_count": group.support_count,
                    "pass_ids": list(group.pass_ids),
                    "languages": list(group.languages),
                    "variants": list(group.variants),
                    "explicit_currency_votes": group.explicit_currency_votes,
                    "arithmetic_pass_ids": list(group.arithmetic_pass_ids),
                    "matched_label": group.matched_label,
                    "label_kind": group.label_kind,
                    "ranking_warnings": list(group.ranking_warnings),
                }
                for group in groups
            ],
            "ocr": {
                "passes": [
                    {
                        "pass_id": ocr_pass.pass_id,
                        "variant": ocr_pass.variant,
                        "language": ocr_pass.language,
                        "psm": ocr_pass.psm,
                        "average_confidence": ocr_pass.average_confidence,
                        "raw_text": "\n".join(line.text for line in ocr_pass.lines),
                        "lines": [
                            {
                                "text": line.text,
                                "confidence": line.confidence,
                                "top": line.top,
                                "bottom": line.bottom,
                            }
                            for line in ocr_pass.lines
                        ],
                    }
                    for ocr_pass in passes
                ]
            },
            "candidates": [
                {
                    "amount": candidate.amount,
                    "currency": candidate.currency,
                    "line": candidate.line,
                    "label": candidate.label,
                    "label_kind": candidate.label_kind,
                    "score": candidate.score,
                    "reasons": list(candidate.reasons),
                    "pass_id": candidate.pass_id,
                }
                for candidate in candidates
            ],
        }
    return InterpretationResult(
        total=total,
        currency=currency,
        evidence_grade=grade,
        matched_label=winner.matched_label if winner else None,
        label_kind=(
            winner.label_kind if winner and winner.label_kind in {"payment", "fallback"} else None
        ),
        warnings=warnings,
        diagnostics=diagnostics_payload,
    )


def _rank_warnings(
    groups: tuple[CandidateGroup, ...], currency_context: str, degraded: bool
) -> tuple[OcrWarning, ...]:
    warnings: list[OcrWarning] = []
    if not groups:
        warnings.append(
            OcrWarning(
                code="no_candidate",
                message="No payment or fallback total label with a monetary value was extracted.",
            )
        )
        return tuple(warnings)
    winner = groups[0]
    conflicting = sorted(
        currency
        for currency, count in winner.explicit_currency_votes.items()
        if count > 0 and currency != "INR"
    )
    if conflicting:
        warnings.append(
            OcrWarning(
                code="currency_conflict",
                message=f"Conflicting explicit currency marker(s): {', '.join(conflicting)}",
            )
        )
    if len(groups) > 1 and groups[1].support_count >= winner.support_count:
        warnings.append(
            OcrWarning(
                code="competing_total",
                message="A competing total has equal or greater OCR-pass support.",
            )
        )
    for warning in winner.ranking_warnings:
        warnings.append(OcrWarning(code="ranking_warning", message=warning))
    if degraded:
        warnings.append(
            OcrWarning(
                code="degraded_processing",
                message="Processing was degraded by pass failures or deadline pressure.",
            )
        )
    if currency_context == "INR" and winner.currency != "INR":
        warnings.append(
            OcrWarning(
                code="currency_context_mismatch",
                message="Best-supported total conflicts with INR context.",
            )
        )
    return tuple(warnings)


def _evidence_grade(
    groups: tuple[CandidateGroup, ...], warnings: tuple[OcrWarning, ...], degraded: bool
) -> str:
    if not groups:
        return "none"
    winner = groups[0]
    warning_codes = {warning.code for warning in warnings}
    runner_safe = len(groups) == 1
    if len(groups) > 1:
        runner = groups[1]
        score_gap = winner.score - runner.score
        runner_safe = score_gap >= (18 if runner.label_kind == "payment" else 20)
    language_support = len(winner.languages) >= 2 and winner.support_count >= 3
    arithmetic_support = len(winner.arithmetic_pass_ids) >= 2
    explicit_inr_marker = winner.explicit_currency_votes.get("INR", 0) > 0
    if (
        winner.label_kind == "payment"
        and runner_safe
        and explicit_inr_marker
        and not degraded
        and not ({"ranking_warning", "currency_conflict", "competing_total"} & warning_codes)
        and (language_support or arithmetic_support)
    ):
        return "strong"
    return "review"


def _normalized_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    chars: list[str] = []
    for char in normalized:
        category = unicodedata.category(char)
        if category in {"Mn", "Cf"}:
            continue
        try:
            chars.append(str(unicodedata.decimal(char)))
        except (TypeError, ValueError):
            chars.append(char)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


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


def _classify_line(text: str) -> tuple[str, Optional[str], Optional[str], int]:
    lowered = _normalized_search_text(text).lower()
    for label in NEGATIVE_TOTAL_LABELS:
        if label in lowered:
            return "component", label, "ignore", -90
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


def _parse_amount(token: str) -> Decimal:
    compact = token.replace(" ", "").replace(",", "")
    try:
        return Decimal(compact).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ValueError(f"Invalid amount token: {token}") from error


def _format_decimal(amount: Decimal) -> str:
    return format(amount.quantize(Decimal("0.01")), "f")


def _document_currency(lines: tuple[OcrLine, ...]) -> str:
    votes: Counter[str] = Counter()
    for line in lines:
        normalized = _normalized_search_text(line.text)
        for pattern, currency in CURRENCY_TOKEN_PATTERNS:
            votes[currency] += len(pattern.findall(normalized))
    return votes.most_common(1)[0][0] if votes else "INR"


def _candidates_for_pass(
    ocr_pass: OcrPassResult, image_height: int, currency_context: str
) -> tuple[Candidate, ...]:
    fallback_currency = _document_currency(ocr_pass.lines)
    found: list[Candidate] = []
    for line_index, line in enumerate(ocr_pass.lines):
        searchable = _normalized_search_text(line.text)
        label_kind, label, component_role, label_points = _classify_line(searchable)
        matches = list(MONEY_PATTERN.finditer(searchable))
        for match_index, match in enumerate(matches):
            explicit_currency = _currency_from_marker(
                match.group("prefix")
            ) or _currency_from_marker(match.group("suffix"))
            amount_token = match.group("amount")
            if label_kind == "unlabeled" and not explicit_currency and "." not in amount_token:
                continue
            if match.end() < len(searchable) and searchable[match.end() :].lstrip().startswith("%"):
                continue
            score = float(label_points)
            reasons: list[str] = []
            if label:
                reasons.append(f"{label_kind} {label} label {label_points:+d}")
            vertical_ratio = min(1.0, max(0.0, line.bottom / float(max(1, image_height))))
            score += round(vertical_ratio * 14, 2)
            confidence_points = round(max(0.0, line.confidence) / 10.0, 2)
            score += confidence_points
            if match_index == len(matches) - 1:
                score += 8
            if explicit_currency:
                score += 7
                if explicit_currency == "INR":
                    score += 5
            currency = explicit_currency or fallback_currency or currency_context
            found.append(
                Candidate(
                    amount=_format_decimal(_parse_amount(amount_token)),
                    currency=currency,
                    explicit_currency=explicit_currency is not None,
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
                    reasons=tuple(reasons),
                )
            )
    found.sort(key=lambda candidate: candidate.score, reverse=True)
    return tuple(found)


def _arithmetic_matches(candidates: tuple[Candidate, ...]) -> dict[str, tuple[str, ...]]:
    by_pass: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_pass[candidate.pass_id].append(candidate)
    matches: dict[str, list[str]] = defaultdict(list)
    for pass_id, pass_candidates in by_pass.items():
        finals = [
            candidate
            for candidate in pass_candidates
            if candidate.label_kind in {"payment", "fallback"}
        ]
        if not finals:
            continue
        final = max(finals, key=lambda candidate: (candidate.score, candidate.line_index))
        components = [
            candidate
            for candidate in pass_candidates
            if candidate.label_kind == "component"
            and candidate.component_role in {"addition", "subtraction"}
        ]
        if len(components) < 2:
            continue
        calculated = Decimal("0")
        for component in components:
            amount = Decimal(component.amount)
            calculated += -amount if component.component_role == "subtraction" else amount
        displayed = Decimal(final.amount)
        tolerance = max(Decimal("0.50"), displayed * Decimal("0.005"))
        if abs(calculated - displayed) <= tolerance:
            matches[final.amount].append(pass_id)
    return {amount: tuple(sorted(set(pass_ids))) for amount, pass_ids in matches.items()}


def _aggregate_candidates(
    candidates: tuple[Candidate, ...], currency_context: str
) -> tuple[CandidateGroup, ...]:
    arithmetic = _arithmetic_matches(candidates)
    grouped: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.label_kind in {"payment", "fallback"}:
            grouped[candidate.amount].append(candidate)
    groups: list[CandidateGroup] = []
    for amount, amount_candidates in grouped.items():
        pass_ids = tuple(sorted({candidate.pass_id for candidate in amount_candidates}))
        languages = tuple(sorted({candidate.language for candidate in amount_candidates}))
        variants = tuple(sorted({candidate.variant for candidate in amount_candidates}))
        explicit_votes = Counter(
            candidate.currency for candidate in amount_candidates if candidate.explicit_currency
        )
        currency = "INR"
        if currency_context == "INR":
            currency = "INR"
        elif explicit_votes:
            currency = explicit_votes.most_common(1)[0][0]
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
        score = (
            max(candidate.score for candidate in amount_candidates)
            + min(36, len(pass_ids) * 5)
            + max(0, len(languages) - 1) * 14
            + max(0, len(variants) - 1) * 5
            + min(12, len(arithmetic.get(amount, ())) * 4)
        )
        groups.append(
            CandidateGroup(
                amount=amount,
                currency=currency,
                score=round(score, 2),
                support_count=len(pass_ids),
                pass_ids=pass_ids,
                languages=languages,
                variants=variants,
                explicit_currency_votes=dict(explicit_votes),
                arithmetic_pass_ids=arithmetic.get(amount, ()),
                matched_label=best.label,
                label_kind=best.label_kind if best.label_kind in {"payment", "fallback"} else None,
                ranking_warnings=tuple(),
            )
        )
    groups.sort(key=lambda group: (group.score, group.support_count), reverse=True)
    return tuple(_with_ranking_warnings(tuple(groups)))


def _with_ranking_warnings(groups: tuple[CandidateGroup, ...]) -> list[CandidateGroup]:
    amended = list(groups)
    for i, longer in enumerate(groups):
        longer_decimal = Decimal(longer.amount)
        if longer_decimal != longer_decimal.to_integral_value():
            continue
        longer_digits = str(int(longer_decimal))
        for j, shorter in enumerate(groups):
            if i == j or longer.matched_label != shorter.matched_label:
                continue
            shorter_decimal = Decimal(shorter.amount)
            if shorter_decimal != shorter_decimal.to_integral_value():
                continue
            shorter_digits = str(int(shorter_decimal))
            if (
                len(longer_digits) == len(shorter_digits) + 1
                and len(shorter_digits) >= 3
                and longer_digits.endswith(shorter_digits)
                and shorter.support_count >= longer.support_count
            ):
                amended[i] = CandidateGroup(
                    amount=longer.amount,
                    currency=longer.currency,
                    score=round(longer.score - 20, 2),
                    support_count=longer.support_count,
                    pass_ids=longer.pass_ids,
                    languages=longer.languages,
                    variants=longer.variants,
                    explicit_currency_votes=longer.explicit_currency_votes,
                    arithmetic_pass_ids=longer.arithmetic_pass_ids,
                    matched_label=longer.matched_label,
                    label_kind=longer.label_kind,
                    ranking_warnings=(
                        "Possible leading-digit OCR corruption versus alternate candidate.",
                    ),
                )
                break
    amended.sort(key=lambda group: (group.score, group.support_count), reverse=True)
    return amended
