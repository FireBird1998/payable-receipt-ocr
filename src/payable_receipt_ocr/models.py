"""Typed public result model for payable-receipt-ocr."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Literal, Mapping, Optional, Tuple, cast

SCHEMA_VERSION = "payable-receipt-ocr/1"
EvidenceGrade = Literal["strong", "review", "none"]
LabelKind = Literal["payment", "fallback"]


@dataclass(frozen=True)
class RecognitionWarning:
    """A stable warning code with human-readable context."""

    code: str
    message: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RecognitionWarning":
        return cls(code=str(payload["code"]), message=str(payload["message"]))

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class RuntimeProvenance:
    """Runtime identity reported with every recognition result."""

    baseline_id: str
    conformant: bool
    tesseract_version: str
    model_sha256: Mapping[str, str]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RuntimeProvenance":
        raw_hashes = cast(Mapping[str, Any], payload.get("model_sha256", {}))
        return cls(
            baseline_id=str(payload["baseline_id"]),
            conformant=bool(payload["conformant"]),
            tesseract_version=str(payload["tesseract_version"]),
            model_sha256={str(name): str(value) for name, value in raw_hashes.items()},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "conformant": self.conformant,
            "tesseract_version": self.tesseract_version,
            "model_sha256": dict(self.model_sha256),
        }


@dataclass(frozen=True)
class RecognitionResult:
    """A confirmation-only suggestion produced from one receipt image.

    ``strong`` means independent evidence agrees; it never grants permission
    to persist an expense. Diagnostics are retained only when the caller opts
    in during recognition.
    """

    total: Optional[Decimal]
    currency: Optional[str]
    evidence_grade: EvidenceGrade
    requires_confirmation: Literal[True]
    authorizes_persistence: Literal[False]
    matched_label: Optional[str]
    label_kind: Optional[LabelKind]
    warnings: Tuple[RecognitionWarning, ...]
    source_filename: str
    source_dimensions: Tuple[int, int]
    passes_planned: int
    passes_completed: int
    passes_failed: int
    degraded: bool
    deadline_exceeded: bool
    duration_ms: int
    runtime: RuntimeProvenance
    _diagnostics: Optional[Mapping[str, Any]] = field(default=None, repr=False, compare=False)

    @property
    def pass_count(self) -> int:
        """Backward-compatible alias for completed OCR passes."""

        return self.passes_completed

    @property
    def needs_review(self) -> bool:
        """Whether the suggestion lacks strong evidence."""

        return self.evidence_grade != "strong"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RecognitionResult":
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported recognition schema version")

        selected = cast(Mapping[str, Any], payload["result"])
        if selected.get("requires_confirmation") is not True:
            raise ValueError("Recognition results must require confirmation")
        if selected.get("authorizes_persistence") is not False:
            raise ValueError("Recognition results cannot authorize persistence")

        source = cast(Mapping[str, Any], payload["source"])
        processing = cast(Mapping[str, Any], payload["processing"])
        raw_total = selected["total"]
        raw_currency = selected["currency"]
        grade = cast(EvidenceGrade, selected["evidence_grade"])
        if grade == "none" and (raw_total is not None or raw_currency is not None):
            raise ValueError("No-evidence results cannot include amount or currency")

        return cls(
            total=Decimal(str(raw_total)) if raw_total is not None else None,
            currency=str(raw_currency) if raw_currency is not None else None,
            evidence_grade=grade,
            requires_confirmation=True,
            authorizes_persistence=False,
            matched_label=(
                str(selected["matched_label"])
                if selected.get("matched_label") is not None
                else None
            ),
            label_kind=cast(Optional[LabelKind], selected.get("label_kind")),
            warnings=tuple(
                RecognitionWarning.from_payload(cast(Mapping[str, Any], item))
                for item in cast(Tuple[Mapping[str, Any], ...], payload["warnings"])
            ),
            source_filename=str(source["filename"]),
            source_dimensions=(
                int(cast(Tuple[int, int], source["dimensions"])[0]),
                int(cast(Tuple[int, int], source["dimensions"])[1]),
            ),
            passes_planned=int(processing["passes_planned"]),
            passes_completed=int(processing["passes_completed"]),
            passes_failed=int(processing["passes_failed"]),
            degraded=bool(processing["degraded"]),
            deadline_exceeded=bool(processing["deadline_exceeded"]),
            duration_ms=int(processing["duration_ms"]),
            runtime=RuntimeProvenance.from_payload(cast(Mapping[str, Any], payload["runtime"])),
            _diagnostics=cast(Optional[Mapping[str, Any]], payload.get("diagnostics")),
        )

    def to_dict(self, *, include_diagnostics: bool = False) -> Dict[str, Any]:
        """Return the coordinated Python/CLI JSON contract."""

        result: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "filename": self.source_filename,
                "dimensions": list(self.source_dimensions),
            },
            "processing": {
                "passes_planned": self.passes_planned,
                "passes_completed": self.passes_completed,
                "passes_failed": self.passes_failed,
                "degraded": self.degraded,
                "deadline_exceeded": self.deadline_exceeded,
                "duration_ms": self.duration_ms,
            },
            "runtime": self.runtime.to_dict(),
            "result": {
                "total": (
                    format(self.total.quantize(Decimal("0.01")), "f")
                    if self.total is not None
                    else None
                ),
                "currency": self.currency,
                "evidence_grade": self.evidence_grade,
                "requires_confirmation": True,
                "authorizes_persistence": False,
                "matched_label": self.matched_label,
                "label_kind": self.label_kind,
            },
            "warnings": [warning.to_dict() for warning in self.warnings],
        }
        if include_diagnostics:
            if self._diagnostics is None:
                raise ValueError("Diagnostics must be requested during recognition")
            result["diagnostics"] = dict(self._diagnostics)
        return result
