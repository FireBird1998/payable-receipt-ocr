"""Typed public result model for payable-receipt-ocr."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Literal, Mapping, Optional, Tuple

EvidenceGrade = Literal["strong", "review", "none"]


@dataclass(frozen=True)
class RecognitionResult:
    """A confirmation-only suggestion produced from one receipt image.

    ``strong`` means independent evidence agrees; it never grants permission
    to save an expense automatically. ``requires_confirmation`` therefore
    remains true for every successful result.
    """

    total: Optional[Decimal]
    currency: str
    evidence_grade: EvidenceGrade
    requires_confirmation: Literal[True]
    needs_review: bool
    matched_label: Optional[str]
    matched_line: Optional[str]
    warnings: Tuple[str, ...]
    source_filename: str
    source_dimensions: Tuple[int, int]
    pass_count: int
    _payload: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RecognitionResult":
        selected = payload["result"]
        source = payload["source"]
        processing = payload["processing"]
        raw_total = selected["total"]
        return cls(
            total=Decimal(raw_total) if raw_total is not None else None,
            currency=str(selected["currency"]),
            evidence_grade=selected["evidence_grade"],
            requires_confirmation=True,
            needs_review=bool(selected["needs_review"]),
            matched_label=selected["matched_label"],
            matched_line=selected["matched_line"],
            warnings=tuple(str(item) for item in payload["warnings"]),
            source_filename=str(source["filename"]),
            source_dimensions=(int(source["dimensions"][0]), int(source["dimensions"][1])),
            pass_count=int(processing["pass_count"]),
            _payload=payload,
        )

    def to_dict(self, *, include_diagnostics: bool = False) -> Dict[str, Any]:
        """Return a JSON-serializable representation.

        Diagnostics contain OCR text and candidate evidence. They are omitted
        by default because receipt text can contain sensitive information.
        """

        result: Dict[str, Any] = {
            "schema_version": "payable-receipt-ocr/v1",
            "source": {
                "filename": self.source_filename,
                "dimensions": list(self.source_dimensions),
            },
            "processing": {"pass_count": self.pass_count},
            "result": {
                "total": format(self.total, "f") if self.total is not None else None,
                "currency": self.currency,
                "evidence_grade": self.evidence_grade,
                "requires_confirmation": self.requires_confirmation,
                "needs_review": self.needs_review,
                "matched_label": self.matched_label,
                "matched_line": self.matched_line,
            },
            "warnings": list(self.warnings),
        }
        if include_diagnostics:
            result["diagnostics"] = {
                "processing": self._payload["processing"],
                "candidate_groups": self._payload["candidate_groups"],
                "candidates": self._payload["candidates"],
                "ocr": self._payload["ocr"],
            }
        return result
