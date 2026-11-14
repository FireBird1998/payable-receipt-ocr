"""Evidence geometry: processed OCR boxes trace back to original-image coordinates.

Images here are synthetic shapes or synthetic receipt text; no real receipts are used.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from payable_receipt_ocr import recognize
from payable_receipt_ocr._contracts import RuntimeValidation
from payable_receipt_ocr._geometry import (
    SOURCE_REGION_TOLERANCE_PX,
    CoordinateTransform,
    TransformStep,
    region_tolerance,
)
from payable_receipt_ocr._image import load_source_image, prepare_variants

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def _word(text, *, left, top, width=80, height=20, conf="95"):
    return f"5\t1\t1\t1\t1\t1\t{left}\t{top}\t{width}\t{height}\t{conf}\t{text}"


def _rotate_canvas(canvas: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate with OpenCV and return the image plus its pixel-centre affine matrix."""

    height, width = canvas.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    rotated = cv2.warpAffine(
        canvas,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return rotated, matrix


def _corners(left, top, right, bottom):
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def _apply_centre_matrix(matrix: np.ndarray, points):
    # Corner coordinates -> pixel-centre coordinates -> OpenCV matrix -> corner coordinates.
    mapped = []
    for x, y in points:
        cx, cy = x - 0.5, y - 0.5
        mx = matrix[0, 0] * cx + matrix[0, 1] * cy + matrix[0, 2]
        my = matrix[1, 0] * cx + matrix[1, 1] * cy + matrix[1, 2]
        mapped.append((mx + 0.5, my + 0.5))
    return mapped


def _dark_box(image: np.ndarray, *, min_height: int) -> tuple[int, int, int, int]:
    """Return the largest dark filled box as corner-coordinate bounds."""

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = (gray < 128).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(contour) for contour in contours]
    boxes = [box for box in boxes if box[3] >= min_height]
    x, y, w, h = max(boxes, key=lambda box: box[2] * box[3])
    return x, y, x + w, y + h


def _save(tmp_path: Path, name: str, bgr: np.ndarray) -> Path:
    path = tmp_path / name
    Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).save(path)
    return path


def _upright_canvas(width: int, height: int, box: tuple[int, int, int, int]) -> np.ndarray:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    # Long thin rules give the deskew detector stable horizontal structure.
    left, top, right, bottom = box
    for y in range(int(height * 0.12), int(height * 0.95), max(40, height // 9)):
        if top - 15 <= y <= bottom + 15:
            continue  # Keep rules separate from the target box.
        cv2.line(canvas, (int(width * 0.08), y), (int(width * 0.92), y), (0, 0, 0), 2)
    canvas[top:bottom, left:right] = 0
    return canvas


def test_transform_round_trip_is_exact_for_known_points() -> None:
    transform = CoordinateTransform(
        source_dimensions=(900, 700),
        steps=(
            TransformStep.rotation_about_centre("deskew", angle_degrees=3.5, dimensions=(900, 700)),
            TransformStep.scale("resize", 1.7, dimensions=(1530, 1190)),
            TransformStep.translation("pad", 24, 24, dimensions=(1578, 1238)),
            TransformStep.scale("fit-envelope", 0.9, dimensions=(1420, 1114)),
        ),
    )
    points = [(0.0, 0.0), (900.0, 700.0), (123.25, 456.5)]
    round_trip = transform.to_source(transform.to_processed(points))
    for (x, y), (rx, ry) in zip(points, round_trip, strict=True):
        assert rx == pytest.approx(x, abs=1e-9)
        assert ry == pytest.approx(y, abs=1e-9)


@pytest.mark.parametrize(
    ("name", "dimensions", "box", "angle"),
    [
        ("upscaled-and-padded", (500, 360), (180, 150, 330, 200), 0.0),
        ("downscaled", (3000, 2400), (900, 1100, 1500, 1260), 0.0),
        ("deskewed", (900, 700), (300, 330, 560, 390), 4.0),
        ("deskewed-and-upscaled", (520, 420), (160, 200, 330, 240), -3.0),
    ],
)
def test_prepared_variants_trace_a_known_box_to_the_source(
    tmp_path: Path, name, dimensions, box, angle
) -> None:
    width, height = dimensions
    canvas = _upright_canvas(width, height, box)
    expected = _corners(*box)
    if angle:
        canvas, matrix = _rotate_canvas(canvas, angle)
        expected = _apply_centre_matrix(matrix, expected)
    source = load_source_image(_save(tmp_path, f"{name}.png", canvas))

    variants, preprocessing = prepare_variants(source)

    if angle:
        assert abs(preprocessing["deskew_angle_degrees"]) == pytest.approx(abs(angle), abs=0.3)
    for variant in variants:
        transform = variant.transform
        assert transform.source_dimensions == (source.width, source.height)
        assert transform.processed_dimensions == (variant.image.shape[1], variant.image.shape[0])
        left, top, right, bottom = _dark_box(variant.image, min_height=12)
        region = transform.region_to_source(left, top, right, bottom)
        tolerance = region_tolerance(transform)
        assert tolerance >= SOURCE_REGION_TOLERANCE_PX
        for (x, y), (ex, ey) in zip(region.polygon, expected, strict=True):
            assert abs(x - ex) <= tolerance, (variant.name, region.polygon, expected)
            assert abs(y - ey) <= tolerance, (variant.name, region.polygon, expected)
        assert region.clipped is False


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_orientation_maps_display_coordinates_to_stored_pixels(
    tmp_path: Path, orientation: int
) -> None:
    stored_box = (40, 30, 110, 60)
    stored = Image.new("RGB", (240, 160), "white")
    ImageDraw.Draw(stored).rectangle(
        (stored_box[0], stored_box[1], stored_box[2] - 1, stored_box[3] - 1), fill="black"
    )
    exif = Image.Exif()
    exif[0x0112] = orientation
    path = tmp_path / f"oriented-{orientation}.png"
    stored.save(path, exif=exif)

    source = load_source_image(path)

    assert source.exif_orientation == orientation
    assert source.stored_dimensions == (240, 160)
    display_box = _dark_box(source.bgr, min_height=5)
    mapped = source.orientation.to_source(_corners(*display_box))
    xs = [x for x, _ in mapped]
    ys = [y for _, y in mapped]
    assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx(stored_box, abs=1e-9)


@pytest.fixture
def fake_tesseract(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.png"
    # 600x400 has no deskew lines, is upscaled by 2.5 and padded by 24 processed pixels.
    Image.new("RGB", (600, 400), "white").save(source)
    runtime = RuntimeValidation("synthetic", False, "synthetic", {}, tmp_path, "1")
    monkeypatch.setattr("payable_receipt_ocr._engine.validate_runtime", lambda **_: runtime)

    def run_with(records, *, diagnostics=True):
        def run(command, **kwargs):
            return CompletedProcess(command, 0, HEADER + "\n" + "\n".join(records) + "\n", "")

        monkeypatch.setattr("payable_receipt_ocr._ocr.subprocess.run", run)
        return recognize(source, diagnostics=diagnostics)

    return run_with


PAYABLE_ROW = [
    _word("Amount", left=74, top=174, width=90),
    _word("due", left=174, top=174, width=50),
    _word("INR", left=524, top=174, width=60),
    _word("120.00", left=594, top=174, width=100, conf="88.5"),
]


def _source(processed: float) -> float:
    return (processed - 24) / 2.5


def test_diagnostics_carry_word_geometry_scores_and_engine_identity(fake_tesseract) -> None:
    result = fake_tesseract(PAYABLE_ROW)
    diagnostics = result.to_dict(include_diagnostics=True)["diagnostics"]

    coordinates = diagnostics["coordinates"]
    assert coordinates["frame"] == "source"
    assert coordinates["units"] == "pixels"
    assert coordinates["source_dimensions"] == [600, 400]
    assert coordinates["exif_orientation"] == 1
    assert coordinates["tolerance_pixels"] >= SOURCE_REGION_TOLERANCE_PX
    assert set(coordinates["variants"]) == {"normalized-grayscale", "adaptive-threshold"}

    ocr_pass = diagnostics["ocr"]["passes"][0]
    assert ocr_pass["engine"] == "tesseract"
    assert ocr_pass["script"] in {"Latin", "Devanagari"}
    assert ocr_pass["score_scale"] == "tesseract-word-confidence-0-100"
    (line,) = ocr_pass["lines"]
    assert (line["left"], line["top"], line["right"], line["bottom"]) == (74, 174, 694, 194)
    assert [word["text"] for word in line["words"]] == ["Amount", "due", "INR", "120.00"]
    assert line["words"][3]["ocr_score"] == 88.5
    region = line["source_region"]
    assert region["left"] == pytest.approx(_source(74))
    assert region["right"] == pytest.approx(_source(694))
    assert region["top"] == pytest.approx(_source(174))
    assert region["bottom"] == pytest.approx(_source(194))
    assert region["clipped"] is False
    assert len(region["polygon"]) == 4


def test_candidate_evidence_region_covers_only_the_amount_words(fake_tesseract) -> None:
    result = fake_tesseract(PAYABLE_ROW)
    diagnostics = result.to_dict(include_diagnostics=True)["diagnostics"]

    assert result.total == Decimal("120.00")
    candidate = next(item for item in diagnostics["candidates"] if item["amount"] == "120.00")
    assert candidate["region_basis"] == "amount"
    region = candidate["source_region"]
    assert region["left"] == pytest.approx(_source(524))
    assert region["right"] == pytest.approx(_source(694))
    assert region["top"] == pytest.approx(_source(174))
    assert region["bottom"] == pytest.approx(_source(194))
    # OCR scores live beside evidence; they never replace the evidence grade.
    assert "evidence_grade" not in candidate
    assert candidate["ocr_score"] == pytest.approx((95 + 95 + 95 + 88.5) / 4, abs=0.01)


def test_regions_in_padding_are_clipped_to_the_source(fake_tesseract) -> None:
    result = fake_tesseract([_word("Total", left=0, top=0, width=60, height=30), *PAYABLE_ROW])
    lines = result.to_dict(include_diagnostics=True)["diagnostics"]["ocr"]["passes"][0]["lines"]
    region = lines[0]["source_region"]

    assert region["clipped"] is True
    assert region["left"] == 0 and region["top"] == 0
    assert min(x for x, _ in region["polygon"]) < 0


def test_ordinary_results_carry_no_geometry_or_raw_ocr(fake_tesseract) -> None:
    result = fake_tesseract(PAYABLE_ROW, diagnostics=False)
    serialized = json.dumps(result.to_dict())

    for key in ("source_region", "polygon", "coordinates", "words", "Amount", "ocr_score"):
        assert key not in serialized
    assert set(result.to_dict()) == {
        "schema_version",
        "source",
        "processing",
        "runtime",
        "result",
        "warnings",
    }


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is unavailable")
def test_tesseract_evidence_region_matches_rendered_amount_on_a_rotated_bill(
    tmp_path: Path,
) -> None:
    from test_public_interface import HAS_MODELS

    if not HAS_MODELS:
        pytest.skip("Required tessdata models are unavailable")
    font = ImageFont.load_default(size=34)
    canvas = Image.new("RGB", (900, 620), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((50, 40), "SYNTHETIC RECEIPT - TEST DATA", fill="black", font=font)
    draw.text((50, 160), "Item total: INR 700.00", fill="black", font=font)
    draw.text((50, 240), "Delivery fee: INR 42.50", fill="black", font=font)
    prefix, amount = "Amount due: ", "INR 742.50"
    draw.text((50, 320), prefix + amount, fill="black", font=font)
    for y in (130, 300, 400):
        draw.line((40, y, 860, y), fill="black", width=2)
    amount_left = 50 + draw.textlength(prefix, font=font)
    known = draw.textbbox((amount_left, 320), amount, font=font)

    upright = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)
    rotated, matrix = _rotate_canvas(upright, 3.0)
    expected = _apply_centre_matrix(matrix, _corners(*known))
    image_path = _save(tmp_path, "rotated-bill.png", rotated)

    result = recognize(image_path, diagnostics=True, deadline_seconds=60, pass_timeout_seconds=20)
    diagnostics = result.to_dict(include_diagnostics=True)["diagnostics"]

    assert result.total == Decimal("742.50")
    evidence = [
        item
        for item in diagnostics["candidates"]
        if item["amount"] == "742.50" and item["region_basis"] == "amount"
    ]
    assert evidence
    # Glyph boxes from Tesseract and Pillow differ slightly, so compare with a text margin.
    margin = 8.0
    for candidate in evidence:
        polygon = candidate["source_region"]["polygon"]
        for (x, y), (ex, ey) in zip(polygon, expected, strict=True):
            assert abs(x - ex) <= margin, (polygon, expected)
            assert abs(y - ey) <= margin, (polygon, expected)
