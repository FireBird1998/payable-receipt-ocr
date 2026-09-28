from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from payable_receipt_ocr import (
    ConfigurationError,
    InputFileError,
    RecognitionResult,
    RuntimeBaselineError,
    UnsupportedImageError,
    recognize,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _has_models() -> bool:
    candidates = []
    env_path = os.environ.get("PAYABLE_RECEIPT_OCR_TESSDATA_DIR")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    xdg_home = os.environ.get("XDG_DATA_HOME")
    if xdg_home:
        candidates.append(Path(xdg_home).expanduser() / "payable-receipt-ocr" / "tessdata")
    else:
        candidates.append(Path.home() / ".local" / "share" / "payable-receipt-ocr" / "tessdata")
    for candidate in candidates:
        if (candidate / "eng.traineddata").is_file() and (
            candidate / "Devanagari.traineddata"
        ).is_file():
            return True
    return False


HAS_TESSERACT = shutil.which("tesseract") is not None
HAS_MODELS = _has_models()


def test_missing_image_raises_controlled_error() -> None:
    with pytest.raises(InputFileError, match="does not exist"):
        recognize(FIXTURES / "missing.png", currency="INR")


def test_non_inr_currency_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Only INR is supported"):
        recognize(FIXTURES / "clean-screenshot.png", currency="USD")


def test_invalid_runtime_policy_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="runtime_policy must be either"):
        recognize(
            FIXTURES / "clean-screenshot.png",
            currency="INR",
            runtime_policy="invalid",  # type: ignore[arg-type]
        )


def test_inr_fails_closed_without_required_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PAYABLE_RECEIPT_OCR_TESSDATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    with pytest.raises(RuntimeBaselineError, match="Missing required OCR models"):
        recognize(FIXTURES / "clean-screenshot.png", currency="INR")


@pytest.mark.parametrize(("name", "value"), [("deadline_seconds", 0), ("pass_timeout_seconds", 0)])
def test_invalid_resource_budget_is_rejected(name: str, value: float) -> None:
    arguments = {name: value}
    with pytest.raises(ConfigurationError, match="must be greater than zero"):
        recognize(FIXTURES / "clean-screenshot.png", **arguments)


def test_oversized_file_raises_unsupported_image_error(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.png"
    oversized.write_bytes(b"\x00" * (10 * 1024 * 1024 + 1))

    with pytest.raises(UnsupportedImageError, match="10 MiB"):
        recognize(oversized, runtime_policy="development")


def test_corrupt_image_raises_unsupported_image_error(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not-a-real-image")

    with pytest.raises(UnsupportedImageError, match="readable image|decode failed"):
        recognize(corrupt, runtime_policy="development")


def test_decoded_image_limit_raises_unsupported_image_error(tmp_path: Path) -> None:
    huge = tmp_path / "huge.png"
    Image.new("RGB", (5000, 3000), color=(255, 255, 255)).save(huge)

    with pytest.raises(UnsupportedImageError, match="12 megapixel"):
        recognize(huge, runtime_policy="development")


@pytest.mark.integration
@pytest.mark.skipif(
    not (HAS_TESSERACT and HAS_MODELS),
    reason="Tesseract or required tessdata models are unavailable",
)
@pytest.mark.parametrize(
    ("filename", "currency", "expected_total", "expected_grades"),
    [
        ("clean-screenshot.png", "INR", Decimal("1280.50"), {"strong", "review"}),
        ("multiple-totals.png", "INR", Decimal("604.50"), {"strong", "review"}),
        ("wallet-after-total.png", "INR", Decimal("800.00"), {"review"}),
        ("cash-and-change.png", "INR", Decimal("85.47"), {"review"}),
        ("zero-payable.png", "INR", Decimal("0.00"), {"strong", "review"}),
        ("rupee-marker.png", "INR", Decimal("638.00"), {"strong", "review"}),
    ],
)
def test_synthetic_receipts_through_public_interface(
    filename: str,
    currency: str,
    expected_total: Decimal,
    expected_grades: set[str],
) -> None:
    result = recognize(FIXTURES / filename, currency=currency, runtime_policy="development")

    assert isinstance(result, RecognitionResult)
    assert result.total == expected_total
    assert result.currency == currency
    assert result.evidence_grade in expected_grades
    assert result.requires_confirmation is True
    assert result.authorizes_persistence is False


@pytest.mark.integration
@pytest.mark.skipif(
    not (HAS_TESSERACT and HAS_MODELS),
    reason="Tesseract or required tessdata models are unavailable",
)
@pytest.mark.parametrize("filename", ["savings-only.png", "no-payable-label.png"])
def test_images_without_payable_evidence_do_not_suggest_an_amount(filename: str) -> None:
    result = recognize(FIXTURES / filename, currency="INR", runtime_policy="development")

    assert result.total is None
    assert result.currency is None
    assert result.evidence_grade == "none"
    assert result.requires_confirmation is True
    assert result.authorizes_persistence is False


@pytest.mark.integration
@pytest.mark.skipif(
    not (HAS_TESSERACT and HAS_MODELS),
    reason="Tesseract or required tessdata models are unavailable",
)
def test_diagnostics_are_opt_in_at_recognition_time() -> None:
    compact_result = recognize(
        FIXTURES / "clean-screenshot.png",
        currency="INR",
        runtime_policy="development",
    )
    diagnostics_result = recognize(
        FIXTURES / "clean-screenshot.png",
        currency="INR",
        diagnostics=True,
        runtime_policy="development",
    )

    compact = compact_result.to_dict()
    detailed = diagnostics_result.to_dict(include_diagnostics=True)

    assert "diagnostics" not in compact
    assert "diagnostics" in detailed
    assert compact["result"]["requires_confirmation"] is True
    assert compact["result"]["authorizes_persistence"] is False


@pytest.mark.integration
@pytest.mark.skipif(
    not (HAS_TESSERACT and HAS_MODELS),
    reason="Tesseract or required tessdata models are unavailable",
)
def test_recognition_does_not_mutate_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMP_THREAD_LIMIT", "7")

    recognize(
        FIXTURES / "clean-screenshot.png",
        currency="INR",
        runtime_policy="development",
    )

    assert os.environ["OMP_THREAD_LIMIT"] == "7"


@pytest.mark.integration
@pytest.mark.skipif(
    not (HAS_TESSERACT and HAS_MODELS),
    reason="Tesseract or required tessdata models are unavailable",
)
def test_module_cli_returns_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "payable_receipt_ocr",
            str(FIXTURES / "multiple-totals.png"),
            "--currency",
            "INR",
            "--runtime-policy",
            "development",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["result"]["total"] == "604.50"
    assert payload["result"]["requires_confirmation"] is True
    assert payload["result"]["authorizes_persistence"] is False
    assert "diagnostics" not in payload
