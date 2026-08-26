"""Public error types raised by payable-receipt-ocr."""


class ReceiptOcrError(RuntimeError):
    """Base class for controlled receipt-recognition failures."""

    code = "receipt_ocr"
    exit_code = 1


class InputFileError(ReceiptOcrError):
    """The supplied image path does not identify a readable file."""

    code = "input_file"
    exit_code = 3


class UnsupportedImageError(ReceiptOcrError):
    """The supplied file format or dimensions are outside the supported scope."""

    code = "unsupported_image"
    exit_code = 4


class ConfigurationError(ReceiptOcrError):
    """Recognition configuration is invalid."""

    code = "configuration"
    exit_code = 5


class RuntimeBaselineError(ConfigurationError):
    """The local OCR runtime does not match the selected baseline."""

    code = "runtime_baseline"


class OcrEngineError(ReceiptOcrError):
    """Tesseract is unavailable or failed to complete a recognition pass."""

    code = "ocr_engine"
    exit_code = 6
