from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np

EvidenceGrade = Literal["strong", "review", "none"]
LabelKind = Literal["payment", "fallback"]


@dataclass(frozen=True)
class RuntimeBaseline:
    baseline_id: str
    os_name: str
    arch: str
    tesseract_first_line: str
    oem: int
    psm_allowed: tuple[int, ...]
    omp_thread_limit: str
    model_sha256: dict[str, str]


@dataclass(frozen=True)
class RuntimeValidation:
    baseline_id: str
    conformant: bool
    tesseract_version: str
    model_sha256: dict[str, str]
    tessdata_dir: Path
    omp_thread_limit: str


@dataclass(frozen=True)
class SourceImage:
    path: Path
    filename: str
    width: int
    height: int
    bgr: np.ndarray


@dataclass(frozen=True)
class PreparedVariant:
    name: str
    image: np.ndarray


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    top: int
    bottom: int


@dataclass(frozen=True)
class OcrPassResult:
    pass_id: str
    variant: str
    language: str
    psm: int
    average_confidence: float
    lines: tuple[OcrLine, ...]
    malformed_records: int = 0


@dataclass(frozen=True)
class OcrWarning:
    code: str
    message: str
    pass_id: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.pass_id is not None:
            payload["message"] = f"{self.message} ({self.pass_id})"
        return payload


@dataclass(frozen=True)
class Candidate:
    amount: str
    currency: str
    explicit_currency: bool
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
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGroup:
    amount: str
    currency: str
    score: float
    support_count: int
    pass_ids: tuple[str, ...]
    languages: tuple[str, ...]
    variants: tuple[str, ...]
    explicit_currency_votes: dict[str, int]
    arithmetic_pass_ids: tuple[str, ...]
    matched_label: Optional[str]
    label_kind: Optional[str]
    ranking_warnings: tuple[str, ...]


@dataclass(frozen=True)
class InterpretationResult:
    total: Optional[str]
    currency: Optional[str]
    evidence_grade: EvidenceGrade
    matched_label: Optional[str]
    label_kind: Optional[LabelKind]
    warnings: tuple[OcrWarning, ...]
    diagnostics: Optional[dict[str, Any]]
