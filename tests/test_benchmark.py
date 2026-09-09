from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from payable_receipt_ocr import OcrEngineError

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("development_benchmark", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
BENCHMARK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BENCHMARK
SPEC.loader.exec_module(BENCHMARK)


def _result(total="10.00", *, currency="INR", grade="strong", **overrides):
    values = {
        "total": Decimal(total) if total is not None else None,
        "currency": currency,
        "evidence_grade": grade,
        "warnings": [SimpleNamespace(code="sample_warning")],
        "requires_confirmation": True,
        "authorizes_persistence": False,
        "passes_completed": 4,
        "degraded": False,
        "deadline_exceeded": False,
        "runtime": SimpleNamespace(conformant=False, baseline_id="test-baseline"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _case(case_id="case-1", total="10.00", currency="INR", **overrides):
    return {
        "id": case_id,
        "image": "receipt.png",
        "expected_total": total,
        "expected_currency": currency,
        **overrides,
    }


def _manifest(tmp_path: Path, cases: list[dict]) -> Path:
    (tmp_path / "receipt.png").write_bytes(b"synthetic placeholder; OCR is mocked")
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return path


def test_labelled_report_compares_amount_currency_and_null_and_saves_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    manifest = _manifest(
        tmp_path,
        [
            _case("paid", category="payment"),
            _case("blank", None, None, category="no-total"),
            _case("wrong", category="payment"),
            _case("wrong-currency", category="payment"),
        ],
    )
    results = iter(
        [
            _result(),
            _result(None, currency=None, grade="none"),
            _result("9.99"),
            _result(currency="USD", grade="review"),
        ]
    )
    seen_paths = []

    def recognize(path, **kwargs):
        seen_paths.append(path)
        assert kwargs["diagnostics"] is False
        return next(results)

    monkeypatch.setattr(BENCHMARK, "recognize", recognize)
    output = tmp_path / "reports" / "before.json"
    status = BENCHMARK.main(
        [
            "--manifest",
            str(manifest),
            "--repetitions",
            "1",
            "--output",
            str(output),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert status == 1
    assert json.loads(output.read_text()) == report
    assert seen_paths == [tmp_path / "receipt.png"] * 4
    assert [run["exact_match"] for run in report["runs"]] == [True, True, False, False]
    assert report["summary"]["exact_match_rate"] == 0.5
    assert report["summary"]["false_strong_count"] == 1
    assert report["summary"]["no_suggestion_count"] == 1
    assert report["summary"]["confirmation_rate"] == 1.0
    assert report["summary"]["per_category"]["payment"]["exact_match_rate"] == 1 / 3
    assert report["summary"]["per_category"]["no-total"]["exact_match_rate"] == 1.0
    assert report["runs"][0]["observed_total"] == "10.00"
    assert report["runs"][0]["warning_codes"] == ["sample_warning"]
    assert report["environment_eligibility"]["eligible_for_release_gate"] is False


def test_errors_never_match_expected_null_and_are_in_latency_statistics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    manifest = _manifest(tmp_path, [_case("blank", None, None), _case("error", None, None)])
    results = iter([_result(None, currency=None, grade="none"), OcrEngineError("Timed out")])
    clock = iter([0, 100, 1100, 1200, 6200, 7000])
    monkeypatch.setattr(BENCHMARK.time, "perf_counter_ns", lambda: next(clock) * 1_000_000)

    def recognize(*args, **kwargs):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(BENCHMARK, "recognize", recognize)
    assert BENCHMARK.main(["--manifest", str(manifest), "--repetitions", "1"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["exact_match_rate"] == 0.5
    assert report["summary"]["no_suggestion_count"] == 1
    assert report["summary"]["error_counts"] == {"ocr_engine": 1}
    assert report["durations"]["count"] == 2
    assert report["durations"]["p95_ms"] == 5000
    assert report["durations"]["wall_duration_ms"] == 7000
    assert report["runs"][1]["exact_match"] is False


def test_existing_image_arguments_remain_unlabelled_and_repeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    calls = []

    def recognize(path, **kwargs):
        calls.append((path, kwargs))
        return _result(degraded=True, deadline_exceeded=True)

    monkeypatch.setattr(BENCHMARK, "recognize", recognize)
    image = tmp_path / "receipt.png"
    assert BENCHMARK.main([str(image), "--repetitions", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(calls) == 2
    assert "exact_match" not in report["runs"][0]
    assert report["summary"]["exact_match_rate"] is None
    assert report["summary"]["false_strong_count"] is None
    assert report["summary"]["degraded_count"] == 2
    assert report["summary"]["deadline_exceeded_count"] == 2
    assert report["passes"]["success_count"] == 2


@pytest.mark.parametrize(
    "override",
    [
        {"requires_confirmation": False},
        {"authorizes_persistence": True},
    ],
)
def test_confirmation_contract_violations_fail_the_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    override: dict,
) -> None:
    monkeypatch.setattr(BENCHMARK, "recognize", lambda *a, **k: _result(**override))
    assert BENCHMARK.main([str(tmp_path / "receipt.png"), "--repetitions", "1"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["confirmation_invariant_violations"] == 1


@pytest.mark.parametrize(
    "bad_case",
    [
        _case(total="10.0"),
        _case(total="-1.00"),
        _case(total="NaN"),
        _case(total="Infinity"),
        _case(total="01.00"),
        _case(total=10),
        _case(total=None),
        _case(currency=None),
        _case(currency="USD"),
        _case(category=" "),
        _case(image="missing.png"),
        _case(case_id=""),
        {"id": "missing-label", "image": "receipt.png"},
    ],
)
def test_invalid_manifest_is_fully_rejected_before_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    bad_case: dict,
) -> None:
    manifest = _manifest(tmp_path, [_case("valid-first"), bad_case])
    monkeypatch.setattr(BENCHMARK, "recognize", lambda *a, **k: pytest.fail("OCR was called"))
    assert BENCHMARK.main(["--manifest", str(manifest)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Invalid manifest" in captured.err


@pytest.mark.parametrize("cases", [[], [_case(), _case()]])
def test_empty_and_duplicate_case_manifests_are_rejected(tmp_path: Path, cases: list) -> None:
    with pytest.raises(ValueError):
        BENCHMARK.load_manifest(_manifest(tmp_path, cases))


def test_zero_is_a_valid_nonnegative_label(tmp_path: Path) -> None:
    cases = BENCHMARK.load_manifest(_manifest(tmp_path, [_case(total="0.00")]))
    assert cases[0].expected_total == "0.00"


@pytest.mark.parametrize(
    "arguments",
    [[], ["image.png", "--manifest", "cases.json"], ["image.png", "--repetitions", "0"]],
)
def test_invalid_input_modes_are_rejected(arguments: list[str]) -> None:
    assert BENCHMARK.main(arguments) == 2
