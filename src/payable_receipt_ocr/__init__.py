"""Local, payment-aware receipt OCR with mandatory confirmation."""

from .api import recognize
from .errors import (
    ConfigurationError,
    InputFileError,
    OcrEngineError,
    ReceiptOcrError,
    RuntimeBaselineError,
    UnsupportedImageError,
)
from .models import (
    EvidenceGrade,
    RecognitionResult,
    RecognitionWarning,
    RuntimeProvenance,
)

__all__ = [
    "ConfigurationError",
    "EvidenceGrade",
    "InputFileError",
    "OcrEngineError",
    "ReceiptOcrError",
    "RecognitionResult",
    "RecognitionWarning",
    "RuntimeBaselineError",
    "RuntimeProvenance",
    "UnsupportedImageError",
    "recognize",
]

__version__ = "0.1.0a1"
