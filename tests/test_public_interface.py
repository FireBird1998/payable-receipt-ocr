from __future__ import annotations

import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from payable_receipt_ocr import InputFileError, RecognitionResult, recognize

FIXTURES = Path(__file__).parent / "fixtures"


def test_missing_image_raises_controlled_error() -> None:
    with pytest.raises(InputFileError, match="does not exist"):
        recognize(FIXTURES / "missing.png", currency="INR")


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
@pytest.mark.parametrize(
    ("filename", "currency", "expected_total", "expected_grades"),
    [
        ("clean-screenshot.png", "INR", Decimal("1280.50"), {"strong", "review"}),
        ("multiple-totals.png", "INR", Decimal("604.50"), {"strong", "review"}),
        ("angled-photo.jpg", "USD", Decimal("85.47"), {"review"}),
    ],
)
def test_synthetic_receipts_through_public_interface(
    filename: str,
    currency: str,
    expected_total: Decimal,
    expected_grades: set[str],
) -> None:
    result = recognize(FIXTURES / filename, currency=currency)

    assert isinstance(result, RecognitionResult)
    assert result.total == expected_total
    assert result.currency == currency
    assert result.evidence_grade in expected_grades
    assert result.requires_confirmation is True
    assert result.pass_count in {6, 12}


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_compact_output_excludes_sensitive_diagnostics() -> None:
    result = recognize(FIXTURES / "clean-screenshot.png", currency="INR")

    compact = result.to_dict()
    detailed = result.to_dict(include_diagnostics=True)

    assert "diagnostics" not in compact
    assert "diagnostics" in detailed
    assert compact["result"]["requires_confirmation"] is True


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_module_cli_returns_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "payable_receipt_ocr",
            str(FIXTURES / "multiple-totals.png"),
            "--currency",
            "INR",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["result"]["total"] == "604.50"
    assert payload["result"]["requires_confirmation"] is True
    assert "diagnostics" not in payload
