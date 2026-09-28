#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
if [[ -z "${OCR_DOCKER_PLATFORM:-}" ]]; then
  case "$(docker info --format '{{.Architecture}}')" in
    aarch64|arm64) ocr_platform=linux/arm64 ;;
    x86_64|amd64) ocr_platform=linux/amd64 ;;
    *) echo 'Unsupported Docker architecture; set OCR_DOCKER_PLATFORM explicitly.' >&2; exit 2 ;;
  esac
else
  ocr_platform="${OCR_DOCKER_PLATFORM}"
fi
ocr_image="${OCR_DOCKER_IMAGE:-payable-ocr-dev:${ocr_platform#linux/}}"
docker build --platform "${ocr_platform}" --file "${repo_root}/tools/evaluation/docker/Dockerfile" \
  --tag "${ocr_image}" "${repo_root}"
if [[ "$#" -eq 0 ]]; then
  set -- python -m pytest -q -p no:cacheprovider
fi
# Networking is needed only while building/provisioning, never while recognizing.
docker run --rm --platform "${ocr_platform}" --network none \
  --cpus "${OCR_DOCKER_CPUS:-2}" --memory "${OCR_DOCKER_MEMORY:-2g}" \
  --read-only --tmpfs /tmp:rw,nosuid,size=512m --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 256 "${ocr_image}" "$@"
