from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "holdout" / "evaluate.py"
SPEC = importlib.util.spec_from_file_location("holdout_evaluate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
EVALUATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EVALUATE
SPEC.loader.exec_module(EVALUATE)


def _manifest_sha(payload: dict[str, object]) -> str:
    raw = dict(payload)
    raw.pop("manifest_sha256", None)
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_load_manifest_rejects_duplicate_image_sha(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    image = corpus_root / "a.png"
    image.write_bytes(b"same-bytes")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    payload: dict[str, object] = {
        "corpus_version": "v1",
        "frozen_at": "2026-08-26T00:00:00Z",
        "manifest_sha256": "",
        "runtime_baseline_id": "linux-noble-amd64-2026-08",
        "cases": [
            {
                "case_id": "c-1",
                "image_relpath": "a.png",
                "image_sha256": digest,
                "app": "blinkit",
                "capture_type": "screenshot",
                "expected_total": "10.00",
                "expected_currency": "INR",
            },
            {
                "case_id": "c-2",
                "image_relpath": "a.png",
                "image_sha256": digest,
                "app": "swiggy",
                "capture_type": "screenshot",
                "expected_total": "11.00",
                "expected_currency": "INR",
            },
        ],
    }
    payload["manifest_sha256"] = _manifest_sha(payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EVALUATE.ManifestError, match="duplicate image SHA-256"):
        EVALUATE.load_manifest(manifest, corpus_root)


def test_load_manifest_rejects_noncanonical_amount(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    image = corpus_root / "a.png"
    image.write_bytes(b"fixture")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    payload: dict[str, object] = {
        "corpus_version": "v1",
        "frozen_at": "2026-08-26T00:00:00Z",
        "manifest_sha256": "",
        "runtime_baseline_id": "linux-noble-amd64-2026-08",
        "cases": [
            {
                "case_id": "c-1",
                "image_relpath": "a.png",
                "image_sha256": digest,
                "app": "blinkit",
                "capture_type": "screenshot",
                "expected_total": "10.0",
                "expected_currency": "INR",
            }
        ],
    }
    payload["manifest_sha256"] = _manifest_sha(payload)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EVALUATE.ManifestError, match="two-decimal"):
        EVALUATE.load_manifest(manifest, corpus_root)


def test_evaluate_holdout_gate_math_passes_at_95_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Warning:
        def __init__(self, code: str) -> None:
            self.code = code

    cases = [
        EVALUATE.HoldoutCase(
            case_id=f"case-{index}",
            image_path=Path(f"/tmp/image-{index}.png"),
            image_sha256=f"{index:064x}"[:64],
            app="blinkit" if index < 7 else ("swiggy" if index < 14 else "zepto"),
            capture_type="screenshot",
            expected_total="100.00",
            expected_currency="INR",
        )
        for index in range(20)
    ]
    calls = {"count": 0}

    def _fake_recognize(*args, **kwargs):  # type: ignore[no-untyped-def]
        index = calls["count"]
        calls["count"] += 1
        mismatch = index == 19
        return SimpleNamespace(
            total=Decimal("99.99") if mismatch else Decimal("100.00"),
            currency="INR",
            evidence_grade="review" if mismatch else "strong",
            requires_confirmation=True,
            warnings=[_Warning("ok")],
            duration_ms=6000 if mismatch else 4500,
            runtime=SimpleNamespace(conformant=True, baseline_id="linux-noble-amd64-2026-08"),
        )

    monkeypatch.setattr(EVALUATE, "recognize", _fake_recognize)
    _, summary = EVALUATE.evaluate_holdout(
        cases=cases,
        runtime_policy="conformant",
        expected_baseline_id="linux-noble-amd64-2026-08",
    )

    assert summary["exact_match_rate"] == 0.95
    assert summary["false_strong_count"] == 0
    assert summary["confirmation_rate"] == 1.0
    assert summary["p95_duration_ms"] == 4500
    assert summary["gate_passed"] is True


def test_evaluate_holdout_marks_development_runtime_ineligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = EVALUATE.HoldoutCase(
        case_id="case-1",
        image_path=Path("/tmp/image-1.png"),
        image_sha256="0" * 64,
        app="blinkit",
        capture_type="screenshot",
        expected_total="100.00",
        expected_currency="INR",
    )

    monkeypatch.setattr(
        EVALUATE,
        "recognize",
        lambda *_args, **_kwargs: SimpleNamespace(
            total=Decimal("100.00"),
            currency="INR",
            evidence_grade="strong",
            requires_confirmation=True,
            warnings=[],
            duration_ms=1200,
            runtime=SimpleNamespace(conformant=True, baseline_id="linux-noble-amd64-2026-08"),
        ),
    )
    _, summary = EVALUATE.evaluate_holdout(
        cases=[case],
        runtime_policy="development",
        expected_baseline_id="linux-noble-amd64-2026-08",
    )

    assert summary["gates"]["eligible"] is False
    assert summary["gate_passed"] is False
