# payable-receipt-ocr

[![CI](https://github.com/FireBird1998/payable-receipt-ocr/actions/workflows/ci.yml/badge.svg)](https://github.com/FireBird1998/payable-receipt-ocr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-4f46e5.svg)](LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-f97370.svg)](#project-status)

Local, payment-aware receipt OCR that suggests the amount actually paid and always requires human
confirmation. It is tuned for Blinkit, Swiggy, and Zepto checkout screenshots, with deterministic
receipt semantics on top of Tesseract OCR.

> **Alpha software:** this project is an evidence-producing recognizer, not an accounting system.
> Never save an expense without showing the suggestion to a person for confirmation.

## Why this pipeline is different

Ordinary OCR can read every visible number and still select a discount, subtotal, or wallet amount.
This module separates recognition from interpretation:

1. Pillow loads the image and fixes EXIF orientation.
2. OpenCV deskews, normalizes contrast, and creates two image variants.
3. Tesseract runs in adaptive passes — 4 baseline passes first (1 variant × 2 languages × 2 page
   layouts); if the result is not `strong`, up to 8 additional passes run (second variant + rescue
   layouts), for at most 12 passes total.
4. Geometric row reconstruction reconnects right-aligned prices with their labels.
5. Payment labels outrank fallback totals; discounts, savings, fees, cash, and change supply
   context instead of becoming the winner.
6. Evidence from independent passes produces `strong`, `review`, or `none`—never automatic write
   permission.

INR recognition requires both the English and Devanagari script models and performs:

```text
up to 2 image variants × 2 languages × 3 page layouts = at most 12 OCR passes
```

**Production scope:** INR is the only currency supported in the current runtime. The recognition
pipeline recognises INR currency markers (₹, Rs., INR) from Blinkit, Swiggy, and Zepto checkout
screenshots.

## Installation

Python 3.10 or newer and the Tesseract executable are required. Both `eng.traineddata` and
`Devanagari.traineddata` must be installed before any recognition; the package does not download
models at runtime.

macOS (development environment):

```bash
brew install tesseract
python -m pip install git+https://github.com/FireBird1998/payable-receipt-ocr.git
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
python -m pip install git+https://github.com/FireBird1998/payable-receipt-ocr.git
```

After cloning the repository, install the pinned, checksum-verified models once:

```bash
./scripts/setup-models.sh
```

The script stores `eng.traineddata` and `Devanagari.traineddata` under the current user's data
directory, where the package discovers them automatically. A custom directory can be supplied with:

```python
recognize("receipt.png", tessdata_dir="/path/to/tessdata")
```

or:

```bash
export PAYABLE_RECEIPT_OCR_TESSDATA_DIR=/absolute/path/to/tessdata
```

Recognition fails closed with `RuntimeBaselineError` when either model is unavailable or its
checksum does not match the pinned value. The models come from the Apache-2.0-licensed
[`tessdata_fast`](https://github.com/tesseract-ocr/tessdata_fast) project.

## Python interface

```python
from payable_receipt_ocr import recognize

result = recognize("zepto-checkout.png", currency="INR")

print(result.total)  # Decimal('289.86') or None
print(result.currency)  # 'INR' or None
print(result.evidence_grade)  # 'strong', 'review', or 'none'
print(result.requires_confirmation)  # always True
print(result.authorizes_persistence)  # always False
print(result.warnings)  # tuple of RecognitionWarning(code=..., message=...)
```

The module's interface is intentionally small. OCR variants, page layouts, Unicode normalization,
candidate ranking, arithmetic corroboration, and ambiguity guards remain implementation details.

All parameters after `image` are keyword-only:

```python
result = recognize(
    "receipt.png",
    currency="INR",  # required; only INR is supported
    tessdata_dir=None,  # explicit model directory
    diagnostics=False,  # opt-in; diagnostics contain raw OCR text
    deadline_seconds=5.0,  # total call wall-time limit
    pass_timeout_seconds=2.0,  # per-pass timeout
    runtime_policy="development",  # "development" or "conformant"
)
```

## Command line

```bash
payable-receipt-ocr receipt.png --currency INR
```

The default output is compact JSON and excludes raw OCR text. Diagnostics are useful for
development but contain the full recognized receipt text and should be treated with the same care
as the receipt image itself:

```bash
payable-receipt-ocr receipt.png --currency INR --diagnostics
```

See [docs/schema/v1.md](docs/schema/v1.md) for all CLI flags and exit codes.

## Result contract

```json
{
  "schema_version": "payable-receipt-ocr/1",
  "source": {
    "filename": "zepto-checkout.png",
    "dimensions": [1080, 1920]
  },
  "processing": {
    "passes_planned": 12,
    "passes_completed": 10,
    "passes_failed": 0,
    "degraded": false,
    "deadline_exceeded": false,
    "duration_ms": 2843
  },
  "runtime": {
    "baseline_id": "linux-noble-amd64-2026-08",
    "conformant": false,
    "tesseract_version": "tesseract 5.5.0",
    "model_sha256": {
      "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
      "Devanagari": "3bbb87c1de2a6a2ef0a97dc041e6eea2723a1c22d638f5e38157a5cd441c12b7"
    }
  },
  "result": {
    "total": "289.86",
    "currency": "INR",
    "evidence_grade": "review",
    "requires_confirmation": true,
    "authorizes_persistence": false,
    "matched_label": "to pay",
    "label_kind": "payment"
  },
  "warnings": [
    {"code": "weak_evidence", "message": "Independent OCR evidence did not meet the strong-suggestion gate."}
  ]
}
```

The full schema reference is in [docs/schema/v1.md](docs/schema/v1.md).

## Supported scope

- JPG, JPEG, PNG, and WebP images up to 10 MiB / 12 megapixels (decoded).
- Blinkit, Swiggy, and Zepto checkout screenshots in INR.
- Payable-total suggestion only. INR is the only production-scope currency.

Not supported: PDFs, HEIC, handwriting, multipage documents, reliable line-item extraction,
merchant/date extraction, USD/EUR/GBP production recognition, receipt storage, authentication, or
an HTTP server.

## Diagnostics and privacy

By default `recognize()` retains no raw OCR text. Pass `diagnostics=True` to include it:

```python
result = recognize("receipt.png", currency="INR", diagnostics=True)
output = result.to_dict(include_diagnostics=True)
```

The `diagnostics` key contains the full recognized text from every completed pass and the ranked
candidate list. This data may include names, amounts, or other personal information visible on the
receipt.

The package makes no network requests or persistent writes during recognition. It writes each
prepared OCR variant to a uniquely named PNG under the system temporary directory (`TMPDIR`),
invokes Tesseract with an isolated environment, and deletes the PNG in a `finally` block.
Tesseract may create additional temporary files; use a `tmpfs` for sensitive deployments.
Filenames passed as the `image` argument appear in `source.filename` in the result; file names
that contain personal information should be scrubbed before the result is logged or transmitted.

## Input envelope

| Limit | Value |
|---|---|
| File size | 10 MiB |
| Decoded pixels (source) | 12 megapixels |
| Processed width | ≤ 1 600 px |
| Processed longest side | ≤ 2 600 px |
| Total call deadline | 5 s (default) |
| Per-pass timeout | 2 s (default) |

## Project status

The implementation is alpha. The accuracy gate required for v1 is:

```text
exact total + currency ≥ 95%   (on ≥ 300 frozen, authorized private holdout cases)
AND false-strong results = 0
AND confirmation required = 100%
AND p95 call duration < 5 s    (on the retained reference runtime)
```

None of these thresholds have been measured on the private holdout corpus. The current version
(`0.1.0a1`) reflects this: v1 remains blocked. See [docs/release/v1-gate.md](docs/release/v1-gate.md)
for the full checklist.

macOS is a supported **development** environment. The conformance environment is
`ubuntu-24.04 / amd64 / tesseract 5.3.4`.

## Historical visual documentation

- [Interactive learning lab](docs/learning-lab.html)
- [Pipeline report](docs/pipeline-report.html)
- [Printable stack map](docs/stack-map.html)

These pages describe the original v4 prototype and are retained as learning material. The
normative current behavior is documented below.

## Reference documentation

- [Architecture](ARCHITECTURE.md) — module structure, call direction, privacy model
- [Schema reference](docs/schema/v1.md) — full JSON contract, field meanings, migration guide
- [v1 release gate](docs/release/v1-gate.md) — what must be done before 1.0
- [ADRs](docs/adr/) — architectural decisions

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --editable '.[dev]'
./scripts/setup-models.sh
ruff check .
ruff format --check .
pytest -m 'not integration'         # portable tests; no Tesseract required
pytest -m integration               # requires Tesseract + models from setup-models.sh
python -m build
twine check dist/*
```

Only synthetic fixtures are committed. See [CONTRIBUTING.md](CONTRIBUTING.md) before adding test
data.

## License

The package is available under the [MIT License](LICENSE). Its dependencies and optional trained
data retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
