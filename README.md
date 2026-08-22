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
3. Tesseract runs page segmentation modes 4, 6, and 11 in English and, when configured,
   Devanagari.
4. Geometric row reconstruction reconnects right-aligned prices with their labels.
5. Payment labels outrank fallback totals; discounts, savings, fees, cash, and change supply
   context instead of becoming the winner.
6. Evidence from independent passes produces `strong`, `review`, or `none`—never automatic write
   permission.

With the optional Devanagari model, the default configuration performs:

```text
2 image variants × 2 languages × 3 page layouts = 12 OCR passes
```

## Installation

Python 3.10 or newer and the Tesseract executable are required.

macOS:

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

The package runs six English passes if no Devanagari model is configured. To enable twelve-pass
recognition, place `Devanagari.traineddata` in a private model directory and either pass
`tessdata_dir=...` or set:

```bash
export PAYABLE_RECEIPT_OCR_TESSDATA_DIR=/absolute/path/to/tessdata
```

The model is available from the Apache-2.0-licensed
[`tessdata_fast`](https://github.com/tesseract-ocr/tessdata_fast) project.

## Python interface

```python
from payable_receipt_ocr import recognize

suggestion = recognize("zepto-checkout.png", currency="INR")

print(suggestion.total)  # Decimal('289.86') or None
print(suggestion.currency)  # INR
print(suggestion.evidence_grade)  # strong, review, or none
print(suggestion.requires_confirmation)  # always True
print(suggestion.warnings)
```

The module's interface is intentionally small. OCR variants, page layouts, Unicode normalization,
candidate ranking, arithmetic corroboration, and ambiguity guards remain implementation details.

## Command line

```bash
payable-receipt-ocr receipt.png --currency INR
```

The default JSON is compact and excludes raw OCR text. Diagnostics are useful for development but
may contain sensitive receipt text:

```bash
payable-receipt-ocr receipt.png --currency INR --diagnostics
```

## Result contract

```json
{
  "schema_version": "payable-receipt-ocr/v1",
  "result": {
    "total": "289.86",
    "currency": "INR",
    "evidence_grade": "review",
    "requires_confirmation": true,
    "needs_review": true,
    "matched_label": "to pay",
    "matched_line": "To Pay ... 289.86"
  },
  "warnings": []
}
```

## Supported scope

- JPG, JPEG, PNG, and WebP images up to 30 megapixels.
- English digital receipts and Indian grocery/delivery checkout screenshots.
- INR, USD, EUR, and GBP currency markers.
- Payable-total suggestion only.

Not supported: PDFs, HEIC, handwriting, multipage documents, reliable line-item extraction,
merchant/date extraction, receipt storage, authentication, or an HTTP server.

## Project status

The v4 algorithm reached 35/35 exact total-and-currency matches on a tuned exploratory corpus, with
zero incorrect results graded `strong` and zero confirmation violations. That corpus is not an
independent or redistribution-safe benchmark. Production-readiness remains unproven until a frozen,
authorized holdout of at least 30 unseen screenshots—10 per supported app—passes:

```text
exact total + currency ≥ 90%
AND false-strong results = 0
AND confirmation required = 100%
```

The first release is therefore `0.1.0a1`, not `1.0`.

## Visual documentation

- [Interactive learning lab](docs/learning-lab.html)
- [Pipeline report](docs/pipeline-report.html)
- [Printable stack map](docs/stack-map.html)

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --editable '.[dev]'
ruff check .
ruff format --check .
pytest
python -m build
twine check dist/*
```

Only synthetic fixtures are committed. See [CONTRIBUTING.md](CONTRIBUTING.md) before adding test
data.

## License

The package is available under the [MIT License](LICENSE). Its dependencies and optional trained
data retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
