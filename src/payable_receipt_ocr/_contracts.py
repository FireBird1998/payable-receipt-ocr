from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np

from ._geometry import CoordinateTransform, SourceRegion

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
    # Pixel dimensions as stored in the file, before EXIF orientation is applied.
    stored_dimensions: tuple[int, int]
    exif_orientation: int
    # Maps stored pixels to the oriented frame reported as ``source.dimensions``.
    orientation: CoordinateTransform


@dataclass(frozen=True)
class PreparedVariant:
    name: str
    image: np.ndarray
    # Maps oriented source pixels to this variant's processed pixels.
    transform: CoordinateTransform


@dataclass(frozen=True)
class OcrWord:
    """One recognized word with its box in processed-image pixels.

    ``score`` is the engine's own recognition score (Tesseract: word confidence on a
    0-100 scale). ``None`` means the engine reported no score, which differs from zero.
    It is never an evidence grade.
    """

    text: str
    left: int
    top: int
    right: int
    bottom: int
    score: Optional[float]


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    top: int
    bottom: int
    left: int = 0
    right: int = 0
    words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True)
class OcrPassResult:
    pass_id: str
    variant: str
    language: str
    psm: int
    average_confidence: float
    lines: tuple[OcrLine, ...]
    malformed_records: int = 0
    engine: str = "tesseract"
    score_scale: str = "tesseract-word-confidence-0-100"
    # Maps oriented source pixels to the processed pixels this pass read.
    transform: Optional[CoordinateTransform] = None

    @property
    def script(self) -> str:
        return _SCRIPTS.get(self.language, self.language)

    def source_region(
        self, left: float, top: float, right: float, bottom: float
    ) -> Optional[SourceRegion]:
        if self.transform is None:
            return None
        return self.transform.region_to_source(left, top, right, bottom)


_SCRIPTS = {"eng": "Latin", "Devanagari": "Devanagari"}


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
    # Evidence location in source pixels: the amount's own words when they can be
    # identified ("amount"), otherwise the whole OCR line ("line").
    source_region: Optional[SourceRegion] = None
    region_basis: Optional[str] = None


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
