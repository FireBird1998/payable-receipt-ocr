"""Small public interface for the receipt-recognition module."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from PIL import UnidentifiedImageError

from ._engine import process_receipt
from .errors import InputFileError, UnsupportedImageError
from .models import RecognitionResult

PathLike = Union[str, Path]


def recognize(
    image: PathLike,
    *,
    currency: str = "UNKNOWN",
    tessdata_dir: Optional[PathLike] = None,
    pass_timeout_seconds: float = 15.0,
) -> RecognitionResult:
    """Suggest the payable total visible in a receipt screenshot.

    The function performs no network requests and writes no files. Tesseract
    must be installed locally. A result is evidence for a user-facing
    suggestion and always requires confirmation before persistence.
    """

    try:
        image_path = Path(image).expanduser().resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise InputFileError(
            "Receipt image does not exist or is not readable: {}".format(image)
        ) from error

    model_path = Path(tessdata_dir).expanduser() if tessdata_dir is not None else None
    try:
        payload = process_receipt(
            image_path,
            currency_context=currency,
            tessdata_dir=model_path,
            pass_timeout_seconds=pass_timeout_seconds,
        )
    except UnidentifiedImageError as error:
        raise UnsupportedImageError(
            "The file is not a readable image: {}".format(image_path)
        ) from error
    return RecognitionResult.from_payload(payload)
