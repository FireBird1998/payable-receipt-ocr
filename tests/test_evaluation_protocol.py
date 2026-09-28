"""Contract tests for frozen labels and accounting, independent of OCR quality."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "evaluation" / "protocol.py"
SPEC = importlib.util.spec_from_file_location("expansion_protocol", MODULE_PATH)
assert SPEC and SPEC.loader
PROTOCOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROTOCOL)
EXAMPLE = ROOT / "tools" / "evaluation" / "example"


@pytest.fixture
def inputs():
    return (
        json.loads((EXAMPLE / "manifest.json").read_text()),
        json.loads((EXAMPLE / "observations.json").read_text()),
    )


def seal(manifest):
    manifest["manifest_sha256"] = PROTOCOL.canonical_hash(manifest)
    return manifest


def test_frozen_synthetic_replay_distinguishes_evidence_and_errors(inputs):
    manifest, observations = inputs
    report = PROTOCOL.score(manifest, observations)
    assert report["primary"]["case_count"] == 4
    assert report["primary"]["exact_payable_rate"] == 1
    assert report["primary"]["evidence_correct_payable_rate"] == 0.5
    assert report["primary"]["negative_control_rate"] == 0.5
    assert report["primary"]["strong_wrong_field"] == 1
    assert report["primary"]["errors"] == 1
    assert report["primary"]["abstentions"] == 1  # The error is not successful abstention.
    assert report["primary"]["confirmation_rate"] == 1
    assert report["stability"] == {
        "distinct_images": 4,
        "stable_images": 4,
        "calls": 12,
    }
    assert report["latency_ms"]["p95"] == 9000  # Includes failed calls and initialization.
    assert report["all_calls"]["case_count"] == 12
    assert report["release_qualification"] is False
    assert report["resources"]["process_peak_mib"] == {"measured_calls": 0, "max": None}
    assert report["cohorts"]["family_language"]["utility/en"]["case_count"] == 2
    serialized = json.dumps(report)
    assert '"image"' not in serialized and '"source_region"' not in serialized


def test_old_date_window_and_new_abstention_are_scored_separately(inputs):
    manifest, observations = inputs
    for row in observations["runs"]:
        if row["case_id"] == "date-window":
            row.update(
                total="12.50",
                currency="INR",
                grade="strong",
                source_region=[20, 20, 120, 40],
                source_role="other",
            )
    report = PROTOCOL.score(manifest, observations)
    assert report["primary"]["historical_matches"] == 1
    assert report["primary"]["negative_control_rate"] == 0
    assert report["primary"]["false_strong"] == 1


def test_unlocated_strong_evidence_is_not_a_correct_field(inputs):
    manifest, observations = inputs
    for row in observations["runs"]:
        if row["case_id"] == "zero":
            row.update(source_region=None, source_role=None)
    report = PROTOCOL.score(manifest, observations)
    assert report["primary"]["strong_unlocated"] == 1
    assert report["primary"]["strong_wrong_field"] == 0
    assert report["primary"]["evidence_correct_payable_rate"] == 0.5


def test_repeat_failure_cannot_disappear_behind_first_run_accuracy(inputs):
    manifest, observations = inputs
    row = next(
        r for r in observations["runs"] if r["case_id"] == "payable" and r["repetition"] == 2
    )
    row.update(
        total="99.99",
        requires_confirmation=False,
        authorizes_persistence=True,
        grade="strong",
    )
    report = PROTOCOL.score(manifest, observations)
    assert report["primary"]["exact_payable_rate"] == 1
    assert report["all_calls"]["false_strong"] == 1
    assert report["all_calls"]["confirmation_violations"] == 1
    assert report["all_calls"]["persistence_violations"] == 1
    assert report["stability"]["stable_images"] == 3


@pytest.mark.parametrize(
    "field", ["provenance", "label_reference", "language", "transaction_group"]
)
def test_missing_label_provenance_rejected(inputs, field):
    manifest, _ = inputs
    del manifest["cases"][0][field]
    with pytest.raises(PROTOCOL.ProtocolError):
        PROTOCOL.validate_manifest(seal(manifest))


def test_manifest_tampering_and_duplicate_images_rejected(inputs):
    manifest, _ = inputs
    manifest["cases"][0]["expected"]["total"] = "99.00"
    with pytest.raises(PROTOCOL.ProtocolError, match="hash mismatch"):
        PROTOCOL.validate_manifest(manifest)
    manifest["cases"][1]["image_sha256"] = manifest["cases"][0]["image_sha256"]
    with pytest.raises(PROTOCOL.ProtocolError, match="duplicate image"):
        PROTOCOL.validate_manifest(seal(manifest))


@pytest.mark.parametrize("group", ["transaction_group", "near_duplicate_group"])
def test_correlated_images_cannot_leak_between_splits(inputs, group):
    manifest, _ = inputs
    case = manifest["cases"][1]
    case.update(
        split="qualification",
        provenance="authorized-receipt",
        unseen=True,
        authorization_reference="private-consent-reference",
    )
    case[group] = manifest["cases"][0][group]
    with pytest.raises(PROTOCOL.ProtocolError, match="leaks across splits"):
        PROTOCOL.validate_manifest(seal(manifest))


def test_synthetic_data_cannot_be_called_qualification(inputs):
    manifest, _ = inputs
    manifest["cases"][0]["split"] = "qualification"
    with pytest.raises(PROTOCOL.ProtocolError, match="authorized receipts"):
        PROTOCOL.validate_manifest(seal(manifest))


@pytest.mark.parametrize("total", [0, "0", "-10.00", "NaN", "1.001", "01.00"])
def test_noncanonical_money_is_rejected(inputs, total):
    manifest, _ = inputs
    manifest["cases"][0]["expected"]["total"] = total
    with pytest.raises(PROTOCOL.ProtocolError, match="two-decimal"):
        PROTOCOL.validate_manifest(seal(manifest))


@pytest.mark.parametrize(
    "corruption",
    ["missing", "duplicate", "unknown", "repetition", "hash", "nan", "region"],
)
def test_incomplete_or_malformed_observations_rejected(inputs, corruption):
    manifest, observations = inputs
    if corruption == "missing":
        observations["runs"] = observations["runs"][1:]
    elif corruption == "duplicate":
        observations["runs"].append(copy.deepcopy(observations["runs"][0]))
    elif corruption == "unknown":
        observations["runs"][0]["case_id"] = "unknown"
    elif corruption == "repetition":
        observations["runs"][0]["repetition"] = 9
    elif corruption == "hash":
        observations["manifest_sha256"] = "0" * 64
    elif corruption == "nan":
        observations["runs"][0]["duration_ms"] = float("nan")
    else:
        observations["runs"][0]["source_region"] = [0, 0, 9999, 9999]
    with pytest.raises(PROTOCOL.ProtocolError):
        PROTOCOL.score(manifest, observations)


def test_reference_environment_requires_actual_retained_hardware(inputs):
    manifest, observations = inputs
    env = observations["candidate"]["environment"]
    env.update(kind="reference", os="ubuntu-24.04", arch="amd64")
    with pytest.raises(PROTOCOL.ProtocolError, match="retained_host_id"):
        PROTOCOL.score(manifest, observations)
    env.update(retained_host_id="reserved-example", emulated=True)
    with pytest.raises(PROTOCOL.ProtocolError, match="native Ubuntu"):
        PROTOCOL.score(manifest, observations)


def test_cli_freeze_score_validate_and_no_overwrite(inputs, tmp_path):
    manifest, observations = inputs
    draft = tmp_path / "draft.json"
    frozen = tmp_path / "frozen.json"
    report = tmp_path / "report.json"
    manifest.pop("manifest_sha256")
    draft.write_text(json.dumps(manifest))
    original = draft.read_bytes()

    def run(*args):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *map(str, args)],
            capture_output=True,
            text=True,
        )

    assert run("freeze", draft, "--corpus", EXAMPLE, "--output", frozen).returncode == 0
    frozen_bytes = frozen.read_bytes()
    assert run("freeze", draft, "--corpus", EXAMPLE, "--output", frozen).returncode == 2
    assert frozen.read_bytes() == frozen_bytes and draft.read_bytes() == original
    assert run("validate", frozen, "--corpus", EXAMPLE).returncode == 0
    assert (
        run(
            "score",
            frozen,
            "--observations",
            EXAMPLE / "observations.json",
            "--output",
            report,
        ).returncode
        == 0
    )
    assert json.loads(report.read_text())["primary"]["strong_wrong_field"] == 1


def test_image_bytes_dimensions_and_symlink_are_verified(inputs, tmp_path):
    manifest, _ = inputs
    PROTOCOL.verify_images(manifest, EXAMPLE)
    copy_manifest = copy.deepcopy(manifest)
    copy_manifest["cases"][0]["width"] += 1
    with pytest.raises(PROTOCOL.ProtocolError, match="dimension mismatch"):
        PROTOCOL.verify_images(copy_manifest, EXAMPLE)
    image = tmp_path / "corpus" / "image.png"
    image.parent.mkdir()
    Image.new("RGB", (1, 1)).save(tmp_path / "outside.png")
    image.symlink_to(tmp_path / "outside.png")
    manifest["cases"][0]["image"] = "image.png"
    with pytest.raises(PROTOCOL.ProtocolError, match="symlink"):
        PROTOCOL.verify_images(manifest, image.parent)


def test_retention_keeps_historical_bytes_and_refuses_reuse(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "retain_baseline", ROOT / "tools" / "evaluation" / "retain_baseline.py"
    )
    assert spec and spec.loader
    retain_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retain_module)
    original = tmp_path / "history.json"
    original.write_bytes(b'{ "old_label": "12.50" }\n')
    before = original.read_bytes()

    def fake_git(command, **kwargs):
        assert retain_module.BASELINE_COMMIT in " ".join(command)
        for part in command:
            if part.startswith("--output="):
                Path(part.removeprefix("--output=")).write_bytes(b"retained source archive")

    monkeypatch.setattr(retain_module.subprocess, "run", fake_git)
    output = tmp_path / "snapshot"
    record = retain_module.retain(tmp_path, output, [original])
    assert original.read_bytes() == before
    assert (output / "historical-01.json").read_bytes() == before
    assert record["historical_manifests"][0]["sha256"] == PROTOCOL.file_hash(original)
    with pytest.raises(FileExistsError):
        retain_module.retain(tmp_path, output, [original])
    assert original.read_bytes() == before


def test_nonfinite_candidate_settings_do_not_leave_partial_output(inputs, tmp_path):
    _, observations = inputs
    path = tmp_path / "observations.json"
    output = tmp_path / "report.json"
    observations["candidate"]["settings"]["overflow"] = 1.0
    path.write_text(json.dumps(observations).replace('"overflow": 1.0', '"overflow": 1e999'))
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "score",
            str(EXAMPLE / "manifest.json"),
            "--observations",
            str(path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not output.exists()
    assert str(path) not in result.stderr
