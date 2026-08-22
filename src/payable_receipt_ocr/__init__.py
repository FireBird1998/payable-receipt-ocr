"""Local, payment-aware receipt OCR with mandatory confirmation."""

from .api import recognize
from .errors import (
    ConfigurationError,
    InputFileError,
    OcrEngineError,
    ReceiptOcrError,
    UnsupportedImageError,
)
from .models import EvidenceGrade, RecognitionResult

__all__ = [
    "ConfigurationError",
    "EvidenceGrade",
    "InputFileError",
    "OcrEngineError",
    "ReceiptOcrError",
    "RecognitionResult",
    "UnsupportedImageError",
    "recognize",
]

__version__ = "0.1.0a1"
