#!/usr/bin/env bash
set -euo pipefail

data_root="${XDG_DATA_HOME:-${HOME}/.local/share}"
model_dir="${PAYABLE_RECEIPT_OCR_TESSDATA_DIR:-${data_root}/payable-receipt-ocr/tessdata}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
baseline_file="${script_dir}/../src/payable_receipt_ocr/runtime-baseline.toml"

mkdir -p "${model_dir}"

baseline_value() {
  local key="$1"
  awk -F= -v key="${key}" '
    {
      candidate = $1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", candidate)
      if (candidate == key) {
        value = $2
        gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", value)
        print value
        exit
      }
    }
  ' "${baseline_file}"
}

sha256_file() {
  local file_path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file_path}" | awk '{print $1}'
    return
  fi
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file_path}" | awk '{print $1}'
    return
  fi
  echo "No sha256 tool found (need sha256sum or shasum)." >&2
  exit 1
}

ensure_model() {
  local model_name="$1"
  local model_url="$2"
  local expected_sha256="$3"
  local model_path="${model_dir}/${model_name}.traineddata"

  if [[ -f "${model_path}" ]]; then
    local existing_sha256
    existing_sha256="$(sha256_file "${model_path}")"
    if [[ "${existing_sha256}" == "${expected_sha256}" ]]; then
      echo "${model_name} OCR model already valid: ${model_path}"
      return
    fi
    rm -f "${model_path}"
  fi

  local temporary_model="${model_path}.download"
  trap 'rm -f "${temporary_model}"' RETURN
  curl --fail --location --silent --show-error "${model_url}" --output "${temporary_model}"

  local downloaded_sha256
  downloaded_sha256="$(sha256_file "${temporary_model}")"
  if [[ "${downloaded_sha256}" != "${expected_sha256}" ]]; then
    echo "Downloaded ${model_name} model failed checksum verification" >&2
    exit 1
  fi

  mv "${temporary_model}" "${model_path}"
  trap - RETURN
  echo "${model_name} OCR model ready: ${model_path}"
}

model_commit="$(baseline_value "model_repository_commit")"
eng_sha256="$(baseline_value "eng")"
devanagari_sha256="$(baseline_value "Devanagari")"
model_base_url="https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/${model_commit}"
if [[ -z "${model_commit}" || -z "${eng_sha256}" || -z "${devanagari_sha256}" ]]; then
  echo "Unable to read model identities from ${baseline_file}" >&2
  exit 1
fi

ensure_model \
  "eng" \
  "${model_base_url}/eng.traineddata" \
  "${eng_sha256}"
ensure_model \
  "Devanagari" \
  "${model_base_url}/script/Devanagari.traineddata" \
  "${devanagari_sha256}"
