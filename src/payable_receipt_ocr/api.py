"""Small public interface for the receipt-recognition module."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Union

from ._engine import process_receipt
from .errors import ConfigurationError, InputFileError
from .models import RecognitionResult

PathLike = Union[str, Path]


def recognize(
    image: PathLike,
    *,
    currency: str = "INR",
    tessdata_dir: Optional[PathLike] = None,
    diagnostics: bool = False,
    deadline_seconds: float = 5.0,
    pass_timeout_seconds: float = 2.0,
    runtime_policy: Literal["development", "conformant"] = "development",
) -> RecognitionResult:
    """Suggest the payable total visible in a receipt screenshot.

    The function performs no network requests or persistent writes. Prepared
    images are deleted from the system temporary directory after each local
    Tesseract subprocess. A result is evidence for a user-facing suggestion
    and always requires confirmation before persistence.
    """

    try:
        image_path = Path(image).expanduser().resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise InputFileError(
            "Receipt image does not exist or is not readable: {}".format(image)
        ) from error
    if currency.upper() != "INR":
        raise ConfigurationError("Only INR is supported in the production runtime.")
    if runtime_policy not in {"development", "conformant"}:
        raise ConfigurationError("runtime_policy must be either 'development' or 'conformant'.")
    model_path = Path(tessdata_dir).expanduser() if tessdata_dir is not None else None
    payload = process_receipt(
        image_path,
        currency_context=currency,
        tessdata_dir=model_path,
        pass_timeout_seconds=pass_timeout_seconds,
        deadline_seconds=deadline_seconds,
        diagnostics=diagnostics,
        runtime_policy=runtime_policy,
    )
    return RecognitionResult.from_payload(payload)
