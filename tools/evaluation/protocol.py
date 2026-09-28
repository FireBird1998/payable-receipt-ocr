#!/usr/bin/env python3
"""Freeze and score private expansion experiments; never declare release qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "payable-ocr-evaluation/1"
OBSERVATION_SCHEMA = "payable-ocr-observations/1"
POLICY = "india-payable/1"
FAMILIES = {
    "blinkit",
    "swiggy",
    "zepto",
    "restaurant",
    "retail",
    "pharmacy",
    "fuel",
    "transport",
    "utility",
}
PROVENANCE = {
    "synthetic",
    "vendor-sample",
    "public-bill",
    "unknown-example",
    "authorized-receipt",
}
NEGATIVE_REASONS = {
    "missing-total",
    "ambiguous-due-date",
    "ambiguous-partial-payment",
    "credit",
    "non-payable",
}


class ProtocolError(ValueError):
    """Invalid or inconsistent evaluation input; messages contain no receipt text."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def object_value(value: Any, field: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{field} must be an object")
    return value


def text(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must be nonempty text")
    return value


def digest(value: Any, field: str, length: int = 64) -> None:
    require(
        isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None,
        f"{field} must be a lowercase digest",
    )


def choice(value: Any, values: set[str], field: str) -> None:
    require(isinstance(value, str) and value in values, f"invalid {field}")


def number(value: Any, field: str, *, positive: bool = False) -> None:
    require(
        type(value) in (int, float) and math.isfinite(value) and value >= 0,
        f"{field} must be a finite nonnegative number",
    )
    if positive:
        require(value > 0, f"{field} must be positive")


def amount(total: Any, currency: Any) -> None:
    if total is None:
        require(currency is None, "currency must be null for an absent amount")
    else:
        require(
            isinstance(total, str)
            and re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", total) is not None,
            "amount must be a canonical nonnegative two-decimal string",
        )
        require(currency == "INR", "amount currency must be INR")


def region(value: Any, width: int, height: int) -> None:
    require(
        isinstance(value, list) and len(value) == 4,
        "source_region must have four coordinates",
    )
    for coordinate in value:
        number(coordinate, "source_region coordinate")
    x1, y1, x2, y2 = value
    require(
        x1 < x2 <= width and y1 < y2 <= height,
        "source_region must be inside original image",
    )


def canonical_hash(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy.pop("manifest_sha256", None)
    return hashlib.sha256(
        json.dumps(copy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate_manifest(payload: Any, *, frozen: bool = True) -> dict[str, Any]:
    data = object_value(payload, "manifest")
    require(data.get("schema") == MANIFEST_SCHEMA, "unsupported manifest schema")
    require(data.get("policy_version") == POLICY, "unsupported policy version")
    text(data.get("corpus_version"), "corpus_version")
    timestamp = text(data.get("frozen_at"), "frozen_at")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ProtocolError("frozen_at must be an ISO timestamp") from error
    require(
        parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
        "frozen_at must use UTC",
    )
    historical = data.get("historical_manifests")
    require(isinstance(historical, list), "historical_manifests must be an array")
    for item in historical:
        record = object_value(item, "historical manifest")
        text(record.get("version"), "historical version")
        digest(record.get("sha256"), "historical sha256")
    cases = data.get("cases")
    require(isinstance(cases, list) and bool(cases), "cases must be a nonempty array")
    ids, hashes = set(), set()
    groups: dict[tuple[str, str], str] = {}
    qualification_groups: set[tuple[str, str]] = set()
    for raw in cases:
        case = object_value(raw, "case")
        case_id = text(case.get("id"), "id")
        require(case_id not in ids, "duplicate case id")
        ids.add(case_id)
        digest(case.get("image_sha256"), "image_sha256")
        require(case["image_sha256"] not in hashes, "duplicate image hash")
        hashes.add(case["image_sha256"])
        path = Path(text(case.get("image"), "image"))
        require(
            not path.is_absolute() and ".." not in path.parts,
            "image path must stay within corpus",
        )
        for dimension in ("width", "height"):
            require(
                type(case.get(dimension)) is int and case[dimension] > 0,
                "image dimensions must be positive integers",
            )
        choice(case.get("family"), FAMILIES, "family")
        choice(case.get("language"), {"en", "hi", "mixed"}, "language")
        choice(
            case.get("capture_type"),
            {"screenshot", "photo", "pdf-render"},
            "capture_type",
        )
        choice(case.get("provenance"), PROVENANCE, "provenance")
        choice(case.get("split"), {"development", "qualification"}, "split")
        text(case.get("label_reference"), "label_reference")
        for field in ("transaction_group", "near_duplicate_group"):
            key = (field, text(case.get(field), field))
            require(
                key not in groups or groups[key] == case["split"],
                "duplicate group leaks across splits",
            )
            groups[key] = case["split"]
            if case["split"] == "qualification":
                require(key not in qualification_groups, "correlated qualification cases")
                qualification_groups.add(key)
        if case["split"] == "qualification":
            require(
                case["provenance"] == "authorized-receipt",
                "qualification requires authorized receipts",
            )
            require(case.get("unseen") is True, "qualification requires unseen receipts")
            text(case.get("authorization_reference"), "authorization_reference")
        expected = object_value(case.get("expected"), "expected")
        require(
            {"total", "currency", "source_region", "negative_reason", "role"} <= expected.keys(),
            "expected label is incomplete",
        )
        amount(expected["total"], expected["currency"])
        if expected["total"] is None:
            require(
                expected["role"] == "no-payable" and expected["source_region"] is None,
                "negative control must not label a payable source region",
            )
            choice(expected["negative_reason"], NEGATIVE_REASONS, "negative_reason")
        else:
            require(
                expected["role"] == "final-payable" and expected["negative_reason"] is None,
                "payable labels require final-payable role and no negative reason",
            )
            region(expected["source_region"], case["width"], case["height"])
        if "historical_expected" in case:
            old = object_value(case["historical_expected"], "historical_expected")
            require(
                {"total", "currency", "manifest_sha256"} <= old.keys(),
                "incomplete historical label",
            )
            amount(old["total"], old["currency"])
            require(
                old["manifest_sha256"] in {h["sha256"] for h in historical},
                "historical label must reference a retained manifest",
            )
    if frozen:
        digest(data.get("manifest_sha256"), "manifest_sha256")
        require(data["manifest_sha256"] == canonical_hash(data), "manifest hash mismatch")
    return data


def verify_images(data: dict[str, Any], corpus: Path) -> None:
    from PIL import Image

    root = corpus.resolve()
    for case in data["cases"]:
        path = (root / case["image"]).resolve()
        require(path.is_relative_to(root), "image path escapes corpus via symlink")
        require(
            path.is_file() and file_hash(path) == case["image_sha256"],
            "image hash mismatch",
        )
        with Image.open(path) as image:
            require(
                image.size == (case["width"], case["height"]),
                "image dimension mismatch",
            )


def validate_candidate(raw: Any) -> dict[str, Any]:
    candidate = object_value(raw, "candidate")
    for field in ("id", "engine", "engine_version"):
        text(candidate.get(field), field)
    digest(candidate.get("code_commit"), "code_commit", 40)
    models = object_value(candidate.get("model_sha256"), "model_sha256")
    require(bool(models), "candidate requires model hashes")
    for name, value in models.items():
        text(name, "model name")
        digest(value, "model hash")
    settings = object_value(candidate.get("settings"), "settings")
    require(bool(settings), "candidate requires explicit settings")
    env = object_value(candidate.get("environment"), "environment")
    choice(env.get("kind"), {"development", "reference"}, "environment kind")
    for field in ("os", "arch", "cpu_model"):
        text(env.get(field), field)
    for field in ("logical_cpus", "memory_bytes"):
        require(
            type(env.get(field)) is int and env[field] > 0,
            f"{field} must be positive integer",
        )
    require(type(env.get("emulated")) is bool, "emulated must be explicit")
    if env["kind"] == "reference":
        text(env.get("retained_host_id"), "retained_host_id")
        require(
            env["os"] == "ubuntu-24.04" and env["arch"] == "amd64" and not env["emulated"],
            "reference must be retained native Ubuntu 24.04 amd64",
        )
    return candidate


def validate_observations(manifest: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    data = object_value(payload, "observations")
    require(data.get("schema") == OBSERVATION_SCHEMA, "unsupported observation schema")
    require(
        data.get("manifest_sha256") == manifest["manifest_sha256"],
        "observation manifest mismatch",
    )
    validate_candidate(data.get("candidate"))
    rows = data.get("runs")
    require(isinstance(rows, list) and bool(rows), "runs must be nonempty")
    cases = {c["id"]: c for c in manifest["cases"]}
    repetitions: dict[str, set[int]] = defaultdict(set)
    for raw in rows:
        row = object_value(raw, "run")
        case_id = text(row.get("case_id"), "case_id")
        require(case_id in cases, "run refers to unknown case")
        repeat = row.get("repetition")
        require(
            type(repeat) is int and repeat >= 0,
            "repetition must be nonnegative integer",
        )
        require(repeat not in repetitions[case_id], "duplicate observation")
        repetitions[case_id].add(repeat)
        require(
            {
                "total",
                "currency",
                "error",
                "source_region",
                "source_role",
                "requires_confirmation",
                "authorizes_persistence",
            }
            <= row.keys(),
            "run is incomplete",
        )
        amount(row["total"], row["currency"])
        choice(row.get("grade"), {"none", "review", "strong"}, "grade")
        number(row.get("duration_ms"), "duration_ms")
        for field in ("process_peak_mib", "process_tree_peak_mib", "initialization_ms"):
            require(field in row, f"{field} must be present; null means unmeasured")
            if row[field] is not None:
                number(row[field], field)
        if row["error"] is not None:
            choice(row["error"], {"controlled", "unexpected"}, "error")
            require(
                row["total"] is None and row["grade"] == "none",
                "errors cannot contain suggestions",
            )
        if row["total"] is None:
            require(
                row["grade"] == "none"
                and row["source_region"] is None
                and row["source_role"] is None,
                "absent suggestions cannot carry evidence",
            )
        else:
            require(row["grade"] != "none", "suggestions require review or strong grade")
            if row["source_region"] is not None:
                region(
                    row["source_region"],
                    cases[case_id]["width"],
                    cases[case_id]["height"],
                )
                choice(row["source_role"], {"final-payable", "other"}, "source_role")
            else:
                require(row["source_role"] is None, "unlocated evidence must have null role")
        for field in ("requires_confirmation", "authorizes_persistence"):
            require(
                type(row[field]) is bool or (row["error"] is not None and row[field] is None),
                f"{field} must be explicit on returned results",
            )
    require(set(repetitions) == set(cases), "missing case observations")
    counts = {len(reps) for reps in repetitions.values()}
    require(len(counts) == 1, "every case requires the same repetition count")
    for reps in repetitions.values():
        require(reps == set(range(len(reps))), "repetitions must be contiguous from zero")
    return rows


def overlap(a: list[float], b: list[float]) -> float:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union


def percentile(values: list[float], quantile: float) -> float | None:
    return sorted(values)[math.ceil(quantile * len(values)) - 1] if values else None


def metrics(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for case, row in pairs:
        expected = case["expected"]
        payable = expected["total"] is not None
        error = row["error"] is not None
        suggestion = row["total"] is not None and not error
        exact = not error and (row["total"], row["currency"]) == (
            expected["total"],
            expected["currency"],
        )
        located = row["source_region"] is not None
        evidence = bool(
            payable
            and exact
            and located
            and row["source_role"] == "final-payable"
            and overlap(row["source_region"], expected["source_region"]) >= 0.5
        )
        strong = row["grade"] == "strong"
        counts["payable_cases" if payable else "negative_controls"] += 1
        counts["errors"] += error
        counts["returned_results"] += not error
        counts["exact_payable"] += payable and exact
        counts["evidence_correct_payable"] += evidence
        counts["negative_controls_correct"] += not payable and exact
        counts["wrong_suggestions"] += suggestion and not exact
        counts["abstentions"] += not error and not suggestion
        counts["false_strong"] += strong and not exact
        counts["strong_wrong_field"] += strong and exact and located and not evidence
        counts["strong_unlocated"] += strong and exact and not located
        counts["strong"] += strong
        counts["confirmation_violations"] += not error and row["requires_confirmation"] is not True
        counts["persistence_violations"] += row["authorizes_persistence"] is True
        if "historical_expected" in case:
            old = case["historical_expected"]
            counts["historically_labelled"] += 1
            counts["historical_matches"] += not error and (
                row["total"],
                row["currency"],
            ) == (old["total"], old["currency"])
    result: dict[str, Any] = {"case_count": len(pairs), **dict(counts)}
    for name, numerator, denominator in (
        ("exact_payable_rate", "exact_payable", "payable_cases"),
        ("evidence_correct_payable_rate", "evidence_correct_payable", "payable_cases"),
        ("negative_control_rate", "negative_controls_correct", "negative_controls"),
        ("strong_coverage", "strong", "returned_results"),
    ):
        result[name] = counts[numerator] / counts[denominator] if counts[denominator] else None
    result["error_rate"] = counts["errors"] / len(pairs)
    result["confirmation_rate"] = (
        1 - counts["confirmation_violations"] / counts["returned_results"]
        if counts["returned_results"]
        else None
    )
    return result


def score(manifest: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    rows = validate_observations(manifest, observations)
    cases = {case["id"]: case for case in manifest["cases"]}
    primary = [(cases[r["case_id"]], r) for r in rows if r["repetition"] == 0]
    durations = [r["duration_ms"] for r in rows]
    slices = {}
    for field in ("family", "language", "capture_type", "provenance", "split"):
        slices[field] = {
            value: metrics([(c, r) for c, r in primary if c[field] == value])
            for value in sorted({c[field] for c, _ in primary})
        }
    slices["family_language"] = {
        f"{family}/{language}": metrics(
            [(c, r) for c, r in primary if c["family"] == family and c["language"] == language]
        )
        for family, language in sorted({(c["family"], c["language"]) for c, _ in primary})
    }
    stable = 0
    for case_id in cases:
        outcomes = {
            (
                r["total"],
                r["currency"],
                r["grade"],
                r["error"],
                tuple(r["source_region"] or []),
                r["source_role"],
                r["requires_confirmation"],
                r["authorizes_persistence"],
            )
            for r in rows
            if r["case_id"] == case_id
        }
        stable += len(outcomes) == 1
    resources = {}
    for field in ("process_peak_mib", "process_tree_peak_mib", "initialization_ms"):
        values = [r[field] for r in rows if r[field] is not None]
        resources[field] = {
            "measured_calls": len(values),
            "max": max(values) if values else None,
        }
    return {
        "schema": "payable-ocr-evaluation-report/1",
        "manifest_sha256": manifest["manifest_sha256"],
        "policy_version": manifest["policy_version"],
        "candidate": observations["candidate"],
        "release_qualification": False,
        "primary": metrics(primary),
        "all_calls": metrics([(cases[r["case_id"]], r) for r in rows]),
        "cohorts": slices,
        "stability": {
            "distinct_images": len(cases),
            "stable_images": stable,
            "calls": len(rows),
        },
        "latency_ms": {f"p{int(q * 100)}": percentile(durations, q) for q in (0.5, 0.95, 0.99)},
        "resources": resources,
    }


def reject_json_constant(_: str) -> None:
    raise ProtocolError("nonfinite JSON number")


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(),
        parse_constant=reject_json_constant,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "validate", "score"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        data = validate_manifest(read_json(args.manifest), frozen=args.action != "freeze")
        if args.action in {"freeze", "validate"}:
            require(args.corpus is not None, "freeze/validate requires --corpus")
            verify_images(data, args.corpus)
        if args.action == "freeze":
            require(
                "manifest_sha256" not in data,
                "already frozen: make a new version instead",
            )
            data["manifest_sha256"] = canonical_hash(data)
        elif args.action == "score":
            require(args.observations is not None, "score requires --observations")
            data = score(data, read_json(args.observations))
        if args.action != "validate":
            require(args.output is not None, "freeze/score requires --output")
            encoded = json.dumps(data, indent=2, allow_nan=False) + "\n"
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
        print(f"{args.action}: valid; no release qualification claimed")
        return 0
    except (OSError, ValueError, TypeError, OverflowError):
        # Detailed parser/OS messages can contain private paths or receipt values.
        print(
            "Invalid evaluation input or output already exists; no file overwritten.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
