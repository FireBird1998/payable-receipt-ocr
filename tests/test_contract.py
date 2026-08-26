from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from payable_receipt_ocr import InputFileError, RecognitionResult


def _payload(*, total: str | None = "289.86", currency: str | None = "INR") -> dict:
    grade = "review" if total is not None else "none"
    return {
        "schema_version": "payable-receipt-ocr/1",
        "source": {"filename": "receipt.png", "dimensions": [1080, 1920]},
        "processing": {
            "passes_planned": 6,
            "passes_completed": 4,
            "passes_failed": 1,
            "degraded": True,
            "deadline_exceeded": True,
            "duration_ms": 4990,
        },
        "runtime": {
            "baseline_id": "linux-noble-amd64-2026-08",
            "conformant": False,
            "tesseract_version": "5.5.3",
            "model_sha256": {},
        },
        "result": {
            "total": total,
            "currency": currency,
            "evidence_grade": grade,
            "requires_confirmation": True,
            "authorizes_persistence": False,
            "matched_label": "to pay" if total is not None else None,
            "label_kind": "payment" if total is not None else None,
        },
        "warnings": [
            {
                "code": "deadline_exceeded",
                "message": "The total recognition deadline was reached",
            }
        ],
    }


def test_versioned_result_contract_is_safe_by_default() -> None:
    result = RecognitionResult.from_payload(_payload())

    serialized = result.to_dict()

    assert serialized["schema_version"] == "payable-receipt-ocr/1"
    assert serialized["result"]["total"] == "289.86"
    assert serialized["result"]["requires_confirmation"] is True
    assert serialized["result"]["authorizes_persistence"] is False
    assert "matched_line" not in serialized["result"]
    assert serialized["warnings"] == [
        {
            "code": "deadline_exceeded",
            "message": "The total recognition deadline was reached",
        }
    ]
    assert "diagnostics" not in serialized


def test_diagnostics_cannot_be_added_after_recognition() -> None:
    result = RecognitionResult.from_payload(_payload())

    with pytest.raises(ValueError, match="requested during recognition"):
        result.to_dict(include_diagnostics=True)


def test_no_evidence_has_no_amount_or_currency() -> None:
    serialized = RecognitionResult.from_payload(_payload(total=None, currency=None)).to_dict()

    assert serialized["result"]["total"] is None
    assert serialized["result"]["currency"] is None
    assert serialized["result"]["evidence_grade"] == "none"
    assert serialized["result"]["requires_confirmation"] is True


def test_controlled_errors_have_stable_codes() -> None:
    error = InputFileError("Receipt image is missing")

    assert error.code == "input_file"
    assert str(error) == "Receipt image is missing"


def test_cli_uses_the_input_error_exit_code(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "payable_receipt_ocr",
            str(tmp_path / "missing.png"),
            "--currency",
            "INR",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 3
    assert completed.stdout == ""
    assert "input_file" in completed.stderr


def test_cli_success_contract_is_json_serializable() -> None:
    encoded = json.dumps(RecognitionResult.from_payload(_payload()).to_dict())

    assert json.loads(encoded)["result"]["authorizes_persistence"] is False
