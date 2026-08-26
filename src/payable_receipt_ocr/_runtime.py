from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from ._contracts import RuntimeBaseline, RuntimeValidation
from .errors import RuntimeBaselineError

_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_BASELINE_FILE = Path(__file__).with_name("runtime-baseline.toml")
_MODEL_NAMES = ("eng", "Devanagari")


def _parse_baseline() -> RuntimeBaseline:
    payload: dict[str, str] = {}
    models: dict[str, str] = {}
    in_models = False
    for raw_line in _BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[models]":
            in_models = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_models = False
            continue
        key, _, value = line.partition("=")
        if not _:
            continue
        key = key.strip()
        value = value.strip().strip('"')
        if in_models:
            models[key] = value
        else:
            payload[key] = value
    return RuntimeBaseline(
        baseline_id=payload["baseline_id"],
        os_name=payload["os_name"],
        arch=payload["arch"],
        tesseract_first_line=payload["tesseract_first_line"],
        oem=int(payload["oem"]),
        psm_allowed=tuple(
            int(token.strip()) for token in payload["psm_allowed"].split(",") if token.strip()
        ),
        omp_thread_limit=payload["omp_thread_limit"],
        model_sha256=models,
    )


BASELINE = _parse_baseline()


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_size, int(stat.st_mtime_ns))
    cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    _HASH_CACHE[key] = digest
    return digest


def _discover_tessdata_dir(explicit: Optional[Path]) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    env_path = os.environ.get("PAYABLE_RECEIPT_OCR_TESSDATA_DIR")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        candidates.append(Path(data_home).expanduser() / "payable-receipt-ocr" / "tessdata")
    else:
        candidates.append(Path.home() / ".local" / "share" / "payable-receipt-ocr" / "tessdata")
    for candidate in candidates:
        resolved = candidate.resolve()
        if all((resolved / f"{name}.traineddata").is_file() for name in _MODEL_NAMES):
            return resolved
    raise RuntimeBaselineError(
        "Missing required OCR models. Install eng.traineddata and "
        "Devanagari.traineddata via scripts/setup-models.sh."
    )


def _tesseract_version(timeout_seconds: float) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeBaselineError("Tesseract is not installed or not on PATH.")
    try:
        output = subprocess.run(
            ["tesseract", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as error:  # pragma: no cover - runtime-dependent.
        raise RuntimeBaselineError("Unable to query Tesseract version.") from error
    first_line = output.stdout.splitlines()[0].strip()
    if not first_line:
        raise RuntimeBaselineError("Unable to read the Tesseract version output.")
    return first_line


def _platform_identity() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        os_name = "ubuntu-24.04" if _is_ubuntu_2404() else "linux-other"
    elif system == "darwin":
        os_name = "macos"
    else:
        os_name = system
    arch = "amd64" if machine in {"x86_64", "amd64"} else machine
    return os_name, arch


def _is_ubuntu_2404() -> bool:
    try:
        fields = {}
        for raw_line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = raw_line.partition("=")
            if separator:
                fields[key] = value.strip().strip('"')
    except OSError:
        return False
    return fields.get("ID") == "ubuntu" and fields.get("VERSION_ID") == "24.04"


def validate_runtime(
    *,
    tessdata_dir: Optional[Path],
    runtime_policy: Literal["development", "conformant"],
    timeout_seconds: float,
) -> RuntimeValidation:
    baseline = BASELINE
    resolved_tessdata = _discover_tessdata_dir(tessdata_dir)
    model_hashes: dict[str, str] = {}
    for model_name in _MODEL_NAMES:
        model_path = resolved_tessdata / f"{model_name}.traineddata"
        actual_hash = _sha256(model_path)
        expected_hash = baseline.model_sha256.get(model_name)
        if actual_hash != expected_hash:
            raise RuntimeBaselineError(
                f"Model checksum mismatch for {model_name}.traineddata: expected "
                f"{expected_hash}, got {actual_hash}"
            )
        model_hashes[model_name] = actual_hash

    current_version = _tesseract_version(timeout_seconds)
    current_os, current_arch = _platform_identity()
    conformant = (
        current_version == baseline.tesseract_first_line
        and current_os == baseline.os_name
        and current_arch == baseline.arch
    )

    if runtime_policy == "conformant" and not conformant:
        raise RuntimeBaselineError(
            "Runtime baseline mismatch: expected "
            f"{baseline.os_name}/{baseline.arch} {baseline.tesseract_first_line}."
        )

    return RuntimeValidation(
        baseline_id=baseline.baseline_id,
        conformant=conformant,
        tesseract_version=current_version,
        model_sha256=model_hashes,
        tessdata_dir=resolved_tessdata,
        omp_thread_limit=baseline.omp_thread_limit,
    )
