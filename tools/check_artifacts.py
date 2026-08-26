#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
FORBIDDEN_SEGMENTS = {"private", "holdout", "corpus", "notes"}


def _iter_archive_members(path: Path) -> list[str]:
    file_path = path.as_posix()
    if file_path.endswith(".whl") or file_path.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if file_path.endswith(".tar.gz") or file_path.endswith(".tgz"):
        with tarfile.open(path, "r:gz") as archive:
            return [member.name for member in archive.getmembers() if member.isfile()]
    raise ValueError(f"unsupported artifact format: {file_path}")


def _norm(name: str) -> PurePosixPath:
    return PurePosixPath(name.strip("/"))


def _is_sdist_member_image_allowed(member: PurePosixPath) -> bool:
    parts = member.parts[1:] if member.parts else ()
    if len(parts) < 2:
        return False
    return parts[0] == "tests" and parts[1] == "fixtures"


def _check_member(member: PurePosixPath, *, is_wheel: bool) -> list[str]:
    problems: list[str] = []
    lowered_parts = {part.lower() for part in member.parts}
    lowered_name = member.as_posix().lower()
    suffix = member.suffix.lower()

    if suffix == ".traineddata":
        problems.append(f"contains traineddata file: {member.as_posix()}")
    if lowered_parts & FORBIDDEN_SEGMENTS:
        problems.append(f"contains forbidden private-like path segment: {member.as_posix()}")
    if is_wheel and ("tests" in lowered_parts or "fixtures" in lowered_parts):
        problems.append(f"wheel must not include tests/fixtures: {member.as_posix()}")
    if suffix in IMAGE_SUFFIXES and not is_wheel:
        if not _is_sdist_member_image_allowed(member):
            problems.append(f"sdist image outside tests/fixtures: {member.as_posix()}")
    if is_wheel and suffix in IMAGE_SUFFIXES:
        problems.append(f"wheel must not include receipt image assets: {member.as_posix()}")
    if "/notes/" in lowered_name or lowered_name.startswith("notes/"):
        problems.append(f"contains notes content: {member.as_posix()}")

    return problems


def inspect_artifact(path: Path) -> list[str]:
    members = _iter_archive_members(path)
    is_wheel = path.as_posix().endswith(".whl")
    problems: list[str] = []
    for name in members:
        member = _norm(name)
        problems.extend(_check_member(member, is_wheel=is_wheel))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tools/check_artifacts.py",
        description="Fail if build artifacts include private or disallowed data.",
    )
    parser.add_argument("artifacts", nargs="+", help="Artifact file paths (.whl/.tar.gz/.zip)")
    args = parser.parse_args()

    failures: list[str] = []
    for artifact in args.artifacts:
        path = Path(artifact)
        problems = inspect_artifact(path)
        for problem in problems:
            failures.append(f"{path.as_posix()}: {problem}")

    if failures:
        print("Artifact inspection failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Artifact inspection passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
