"""Private coordinate tracking from OCR input pixels back to the source image.

Coordinates are continuous pixel-corner coordinates: ``(0, 0)`` is the top-left corner
of the top-left pixel and ``(width, height)`` the bottom-right corner of the image. A
box with ``left=10, right=12`` covers pixel columns 10 and 11. Units are pixels of the
frame named by the transform. See ADR-0011.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import cv2

Point = tuple[float, float]
Matrix = tuple[float, float, float, float, float, float]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

# Rounding and resampling error allowed when a processed box is traced to the source,
# before adding one processed pixel expressed in source pixels (see region_tolerance).
SOURCE_REGION_TOLERANCE_PX = 2.0


def _compose(after: Matrix, before: Matrix) -> Matrix:
    """Return the matrix applying ``before`` first and then ``after``."""

    a0, a1, a2, a3, a4, a5 = after
    b0, b1, b2, b3, b4, b5 = before
    return (
        a0 * b0 + a1 * b3,
        a0 * b1 + a1 * b4,
        a0 * b2 + a1 * b5 + a2,
        a3 * b0 + a4 * b3,
        a3 * b1 + a4 * b4,
        a3 * b2 + a4 * b5 + a5,
    )


def _invert(matrix: Matrix) -> Matrix:
    m0, m1, m2, m3, m4, m5 = matrix
    determinant = m0 * m4 - m1 * m3
    if abs(determinant) < 1e-12:
        raise ValueError("Coordinate transform is not invertible")
    i0, i1 = m4 / determinant, -m1 / determinant
    i3, i4 = -m3 / determinant, m0 / determinant
    return (i0, i1, -(i0 * m2 + i1 * m5), i3, i4, -(i3 * m2 + i4 * m5))


def _apply(matrix: Matrix, points: Iterable[Point]) -> tuple[Point, ...]:
    m0, m1, m2, m3, m4, m5 = matrix
    return tuple((m0 * x + m1 * y + m2, m3 * x + m4 * y + m5) for x, y in points)


@dataclass(frozen=True)
class TransformStep:
    """One geometric preprocessing step, mapping its input frame to its output frame."""

    name: str
    matrix: Matrix
    dimensions: tuple[int, int]

    @classmethod
    def scale(cls, name: str, factor: float, *, dimensions: tuple[int, int]) -> "TransformStep":
        # cv2.resize with fx/fy maps pixel corners by exactly that factor.
        return cls(name, (factor, 0.0, 0.0, 0.0, factor, 0.0), dimensions)

    @classmethod
    def translation(
        cls, name: str, dx: float, dy: float, *, dimensions: tuple[int, int]
    ) -> "TransformStep":
        return cls(name, (1.0, 0.0, float(dx), 0.0, 1.0, float(dy)), dimensions)

    @classmethod
    def from_opencv_matrix(
        cls, name: str, matrix: Sequence[Sequence[float]], *, dimensions: tuple[int, int]
    ) -> "TransformStep":
        """Convert an OpenCV pixel-centre affine matrix to pixel-corner coordinates."""

        a0, a1, a2 = (float(value) for value in matrix[0])
        a3, a4, a5 = (float(value) for value in matrix[1])
        return cls(
            name,
            (a0, a1, a2 + 0.5 - 0.5 * (a0 + a1), a3, a4, a5 + 0.5 - 0.5 * (a3 + a4)),
            dimensions,
        )

    @classmethod
    def rotation_about_centre(
        cls, name: str, *, angle_degrees: float, dimensions: tuple[int, int]
    ) -> "TransformStep":
        width, height = dimensions
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_degrees, 1.0)
        return cls.from_opencv_matrix(name, matrix, dimensions=dimensions)

    @classmethod
    def exif_orientation(cls, orientation: int, *, stored: tuple[int, int]) -> "TransformStep":
        """Map stored pixels to the displayed frame, as ``ImageOps.exif_transpose`` does."""

        width, height = float(stored[0]), float(stored[1])
        matrices: dict[int, Matrix] = {
            1: IDENTITY,
            2: (-1.0, 0.0, width, 0.0, 1.0, 0.0),
            3: (-1.0, 0.0, width, 0.0, -1.0, height),
            4: (1.0, 0.0, 0.0, 0.0, -1.0, height),
            5: (0.0, 1.0, 0.0, 1.0, 0.0, 0.0),
            6: (0.0, -1.0, height, 1.0, 0.0, 0.0),
            7: (0.0, -1.0, height, -1.0, 0.0, width),
            8: (0.0, 1.0, 0.0, -1.0, 0.0, width),
        }
        swapped = orientation in {5, 6, 7, 8}
        dimensions = (stored[1], stored[0]) if swapped else (stored[0], stored[1])
        return cls(f"exif-orientation-{orientation}", matrices[orientation], dimensions)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "matrix": [round(value, 9) for value in self.matrix],
            "output_dimensions": list(self.dimensions),
        }


@dataclass(frozen=True)
class SourceRegion:
    """A processed box traced to source pixels.

    ``polygon`` lists the processed box corners (top-left, top-right, bottom-right,
    bottom-left) in source coordinates and is never clipped, so it can extend past the
    image when the box covered padding. The axis-aligned bounds are clipped to the
    source image; ``clipped`` records whether clipping changed anything.
    """

    polygon: tuple[Point, ...]
    left: float
    top: float
    right: float
    bottom: float
    clipped: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "polygon": [[round(x, 3), round(y, 3)] for x, y in self.polygon],
            "left": round(self.left, 3),
            "top": round(self.top, 3),
            "right": round(self.right, 3),
            "bottom": round(self.bottom, 3),
            "clipped": self.clipped,
        }


@dataclass(frozen=True)
class CoordinateTransform:
    """Ordered preprocessing steps from a source frame to a processed frame."""

    source_dimensions: tuple[int, int]
    steps: tuple[TransformStep, ...] = ()

    @property
    def processed_dimensions(self) -> tuple[int, int]:
        return self.steps[-1].dimensions if self.steps else self.source_dimensions

    @property
    def matrix(self) -> Matrix:
        composed = IDENTITY
        for step in self.steps:
            composed = _compose(step.matrix, composed)
        return composed

    @property
    def linear_scale(self) -> float:
        """Processed pixels per source pixel along any axis (rotation is isotropic)."""

        m0, m1, _, m3, m4, _ = self.matrix
        return math.sqrt(abs(m0 * m4 - m1 * m3))

    def then(self, step: TransformStep) -> "CoordinateTransform":
        return CoordinateTransform(self.source_dimensions, self.steps + (step,))

    def to_processed(self, points: Iterable[Point]) -> tuple[Point, ...]:
        return _apply(self.matrix, points)

    def to_source(self, points: Iterable[Point]) -> tuple[Point, ...]:
        return _apply(_invert(self.matrix), points)

    def region_to_source(
        self, left: float, top: float, right: float, bottom: float
    ) -> SourceRegion:
        polygon = self.to_source(((left, top), (right, top), (right, bottom), (left, bottom)))
        width, height = self.source_dimensions
        xs = [x for x, _ in polygon]
        ys = [y for _, y in polygon]
        raw = (min(xs), min(ys), max(xs), max(ys))
        bounds = (
            min(max(raw[0], 0.0), float(width)),
            min(max(raw[1], 0.0), float(height)),
            min(max(raw[2], 0.0), float(width)),
            min(max(raw[3], 0.0), float(height)),
        )
        clipped = any(abs(a - b) > 1e-9 for a, b in zip(raw, bounds, strict=True))
        return SourceRegion(polygon, *bounds, clipped=clipped)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_dimensions": list(self.source_dimensions),
            "processed_dimensions": list(self.processed_dimensions),
            "steps": [step.to_dict() for step in self.steps],
        }


def region_tolerance(transform: CoordinateTransform) -> float:
    """Documented maximum source-pixel error for a traced processed box edge."""

    scale = transform.linear_scale
    return SOURCE_REGION_TOLERANCE_PX + (1.0 / scale if scale > 0 else 0.0)
