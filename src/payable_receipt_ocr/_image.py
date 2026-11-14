from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ._contracts import PreparedVariant, SourceImage
from ._geometry import CoordinateTransform, TransformStep
from .errors import InputFileError, UnsupportedImageError

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 12_000_000
MAX_PROCESSED_PIXELS = 4_500_000
MAX_PROCESSED_WIDTH = 1600
MAX_PROCESSED_LONGEST = 2600
PADDING = 24
EXIF_ORIENTATION_TAG = 0x0112


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
            stored_dimensions = (int(opened.width), int(opened.height))
            orientation = _exif_orientation(opened)
            rgb = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = rgb.size
            if width * height > MAX_SOURCE_PIXELS:
                raise UnsupportedImageError("Decoded image exceeds the 12 megapixel limit.")
            bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except UnidentifiedImageError as error:
        raise UnsupportedImageError(f"The file is not a readable image: {path}") from error
    except OSError as error:
        raise UnsupportedImageError(f"Image decode failed for file: {path}") from error
    orientation_step = TransformStep.exif_orientation(orientation, stored=stored_dimensions)
    if orientation_step.dimensions != (width, height):
        raise UnsupportedImageError(f"Image orientation could not be applied for file: {path}")
    return SourceImage(
        path=path,
        filename=path.name,
        width=width,
        height=height,
        bgr=bgr,
        stored_dimensions=stored_dimensions,
        exif_orientation=orientation,
        orientation=CoordinateTransform(stored_dimensions, (orientation_step,)),
    )


def _exif_orientation(image: Image.Image) -> int:
    # Mirror ImageOps.exif_transpose: values outside 1-8 leave the pixels unchanged.
    orientation = image.getexif().get(EXIF_ORIENTATION_TAG, 1)
    return orientation if isinstance(orientation, int) and 1 <= orientation <= 8 else 1


def prepare_variants(source: SourceImage) -> tuple[tuple[PreparedVariant, ...], dict[str, object]]:
    transform = CoordinateTransform((source.width, source.height))
    deskewed, angle, deskew_step = _deskew(source.bgr)
    if deskew_step is not None:
        transform = transform.then(deskew_step)
    resized, resize_step = _resize_to_envelope(deskewed)
    if resize_step is not None:
        transform = transform.then(resize_step)
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
    height, width = resized.shape[:2]
    transform = transform.then(
        TransformStep.translation(
            "pad", PADDING, PADDING, dimensions=(width + 2 * PADDING, height + 2 * PADDING)
        )
    )
    normalized_variant, normalized_transform = _fit_processed_envelope(
        cv2.copyMakeBorder(normalized, *(PADDING,) * 4, cv2.BORDER_CONSTANT, value=255),
        transform,
    )
    threshold_variant, threshold_transform = _fit_processed_envelope(
        cv2.copyMakeBorder(thresholded, *(PADDING,) * 4, cv2.BORDER_CONSTANT, value=255),
        transform,
    )
    variants = (
        PreparedVariant(
            name="normalized-grayscale", image=normalized_variant, transform=normalized_transform
        ),
        PreparedVariant(
            name="adaptive-threshold", image=threshold_variant, transform=threshold_transform
        ),
    )
    return variants, {
        "deskew_angle_degrees": angle,
        "processed_dimensions": [
            int(normalized_variant.shape[1]),
            int(normalized_variant.shape[0]),
        ],
    }


def _deskew(image: np.ndarray) -> tuple[np.ndarray, float, Optional[TransformStep]]:
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
        return image, 0.0, None

    angles = []
    for detected_line in detected_lines:
        x1, y1, x2, y2 = detected_line[0]
        angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if -12 <= angle <= 12:
            angles.append(angle)
    if not angles:
        return image, 0.0, None

    angle = float(np.median(angles))
    if abs(angle) < 0.15 or abs(angle) > 12:
        return image, 0.0, None
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    step = TransformStep.from_opencv_matrix("deskew", matrix, dimensions=(width, height))
    return rotated, round(angle, 3), step


def _resize_to_envelope(image: np.ndarray) -> tuple[np.ndarray, Optional[TransformStep]]:
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
        return image, None
    resized = cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
    )
    return resized, _scale_step("resize", scale, resized)


def _fit_processed_envelope(
    image: np.ndarray, transform: CoordinateTransform
) -> tuple[np.ndarray, CoordinateTransform]:
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
        return image, transform
    fitted = cv2.resize(
        image,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )
    return fitted, transform.then(_scale_step("fit-envelope", scale, fitted))


def _scale_step(name: str, scale: float, output: np.ndarray) -> TransformStep:
    # Output sizes are rounded, but OpenCV maps pixel corners by exactly fx/fy.
    return TransformStep.scale(name, scale, dimensions=(output.shape[1], output.shape[0]))
