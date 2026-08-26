from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ._contracts import PreparedVariant, SourceImage
from .errors import InputFileError, UnsupportedImageError

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 12_000_000
MAX_PROCESSED_PIXELS = 4_500_000
MAX_PROCESSED_WIDTH = 1600
MAX_PROCESSED_LONGEST = 2600


def load_source_image(path: Path) -> SourceImage:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise UnsupportedImageError(
            f"Unsupported image type: {path.suffix or 'no extension'}. Use JPG, JPEG, PNG, or WebP."
        )
    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise InputFileError(f"Receipt image is not readable: {path}") from error
    if file_size > MAX_FILE_BYTES:
        raise UnsupportedImageError("Receipt image exceeds the 10 MiB input size limit.")
    try:
        with Image.open(path) as opened:
            rgb = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = rgb.size
            if width * height > MAX_SOURCE_PIXELS:
                raise UnsupportedImageError("Decoded image exceeds the 12 megapixel limit.")
            bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except UnidentifiedImageError as error:
        raise UnsupportedImageError(f"The file is not a readable image: {path}") from error
    except OSError as error:
        raise UnsupportedImageError(f"Image decode failed for file: {path}") from error
    return SourceImage(path=path, filename=path.name, width=width, height=height, bgr=bgr)


def prepare_variants(source: SourceImage) -> tuple[tuple[PreparedVariant, ...], dict[str, object]]:
    deskewed, angle = _deskew(source.bgr)
    resized = _resize_to_envelope(deskewed)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    thresholded = cv2.adaptiveThreshold(
        normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        13,
    )
    normalized_variant = _fit_processed_envelope(
        cv2.copyMakeBorder(normalized, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    )
    threshold_variant = _fit_processed_envelope(
        cv2.copyMakeBorder(thresholded, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    )
    variants = (
        PreparedVariant(name="normalized-grayscale", image=normalized_variant),
        PreparedVariant(name="adaptive-threshold", image=threshold_variant),
    )
    return variants, {
        "deskew_angle_degrees": angle,
        "processed_dimensions": [
            int(normalized_variant.shape[1]),
            int(normalized_variant.shape[0]),
        ],
    }


def _deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    height, width = image.shape[:2]
    detected_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 1800,
        threshold=80,
        minLineLength=max(60, int(width * 0.15)),
        maxLineGap=25,
    )
    if detected_lines is None:
        return image, 0.0

    angles = []
    for detected_line in detected_lines:
        x1, y1, x2, y2 = detected_line[0]
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if -12 <= angle <= 12:
            angles.append(angle)
    if not angles:
        return image, 0.0

    angle = float(np.median(angles))
    if abs(angle) < 0.15 or abs(angle) > 12:
        return image, 0.0
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, round(angle, 3)


def _resize_to_envelope(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(width, height)
    pixels = width * height
    scale = min(
        2.5,
        MAX_PROCESSED_WIDTH / max(1.0, float(width)),
        MAX_PROCESSED_LONGEST / max(1.0, float(longest)),
        (MAX_PROCESSED_PIXELS / max(1.0, float(pixels))) ** 0.5,
    )
    if 0.999 <= scale <= 1.001:
        return image
    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
    )


def _fit_processed_envelope(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(width, height)
    pixels = width * height
    scale = min(
        1.0,
        MAX_PROCESSED_WIDTH / max(1.0, float(width)),
        MAX_PROCESSED_LONGEST / max(1.0, float(longest)),
        (MAX_PROCESSED_PIXELS / max(1.0, float(pixels))) ** 0.5,
    )
    if scale >= 0.999:
        return image
    return cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )
