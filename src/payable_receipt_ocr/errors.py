"""Public error types raised by payable-receipt-ocr."""


class ReceiptOcrError(RuntimeError):
    """Base class for controlled receipt-recognition failures."""


class InputFileError(ReceiptOcrError):
    """The supplied image path does not identify a readable file."""


class UnsupportedImageError(ReceiptOcrError):
    """The supplied file format or dimensions are outside the supported scope."""


class ConfigurationError(ReceiptOcrError):
    """Recognition configuration is invalid."""


class OcrEngineError(ReceiptOcrError):
    """Tesseract is unavailable or failed to complete a recognition pass."""
