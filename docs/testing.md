# Testing receipt OCR locally

Use the public `recognize()` pipeline to measure what the current version gets right, where it
returns no suggestion, and where it suggests the wrong amount. Start with a small development set,
then add a synthetic regression fixture whenever you fix a failure.

See the [9 September 2026 development baseline](testing-baseline-2026-09-09.md) for the
initial observations and their limits.

## Prepare the runtime

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --editable '.[dev]'
./scripts/setup-models.sh
.venv/bin/python -m pytest -m 'not integration'
.venv/bin/python -m pytest -m integration
```

Tesseract must be installed separately (`brew install tesseract` on macOS). Both pinned English and
Devanagari models are required. macOS uses the default `development` runtime policy. The reference
conformance runtime is Ubuntu 24.04 / amd64 / Tesseract 5.3.4.

## Run the included capability checks

The committed synthetic manifest is ready to run without supplying private receipts:

```bash
.venv/bin/python tools/benchmark.py \
  --manifest tests/fixtures/capability-cases.json \
  --repetitions 1 \
  --output output/synthetic-capabilities.json
```

These eight cases cover payable totals and images that should return no suggestion. Inspect the
saved report to see each expected answer beside the observed answer, evidence grade, and timing.

## Try a single receipt

```bash
.venv/bin/python -m payable_receipt_ocr private-inputs/receipt.png --currency INR
```

Inspect `result.total`, `result.evidence_grade`, and `warnings`. An evidence grade of `strong`
still requires the person to confirm the amount. Use `--diagnostics` only when you need the raw OCR
text and candidate list to investigate a failure; keep that output with the private images.

## Label a small development set

Create a local `private-inputs/development-cases.json`. Label each image before running OCR so the
expected answer is independent of the model's suggestion. For example:

```json
{
  "cases": [
    {
      "id": "receipt-001",
      "image": "receipt.png",
      "expected_total": "289.86",
      "expected_currency": "INR",
      "category": "checkout"
    },
    {
      "id": "receipt-002",
      "image": "no-total.png",
      "expected_total": null,
      "expected_currency": null,
      "category": "no-total"
    }
  ]
}
```

Image paths resolve relative to the manifest file; absolute paths are also accepted. Every `id`
must be unique. Amount labels must be nonnegative canonical two-decimal strings, such as `0.00`
or `1234.50`, with currency `INR`. Use both values as `null` when the image should produce no
suggestion. A category is optional. All records and image paths are validated before OCR starts.

Keep real images, manifests, and reports private and out of commits and CI artifacts. The
benchmark excludes raw OCR text, but its report contains image paths, amounts, and error messages.
The repository's contribution rules permit only synthetic receipt fixtures in committed tests.

## Run and save a baseline

```bash
.venv/bin/python tools/benchmark.py \
  --manifest private-inputs/development-cases.json \
  --repetitions 1 \
  --output output/development-before.json
```

The report includes expected and observed totals/currencies, exact matches, wrong results marked
`strong`, warning codes, no-suggestion counts, errors, and accuracy by category. It also records
confirmation-contract violations, degraded processing, deadline exhaustion, and p50/p95/p99 wall
times. Latency statistics include failed calls. `wall_duration_ms` covers the complete OCR loop.

Exit status is `0` when every labelled run matches and all returned results preserve confirmation
requirements; `1` means an OCR error, labelled mismatch, or confirmation-contract violation; `2`
means invalid inputs or a report-write error. A mismatch still produces the complete report.

For the existing unlabelled latency workflow:

```bash
.venv/bin/python tools/benchmark.py \
  tests/fixtures/clean-screenshot.png tests/fixtures/multiple-totals.png \
  --repetitions 3 --output output/synthetic-timing.json
```

Unlabelled runs have no accuracy or false-strong rate; `ok` and `success_count` only mean the OCR
call returned a result. A returned result can still contain no amount. Confirmation rate is
calculated across returned results; OCR errors are reported separately and always fail the run.

## Improve one failure at a time

Include clean screenshots, competing totals, discounts/wallet use, small text, wide price columns,
dark backgrounds, blur/rotation, and images without a payable total. Include each app you intend
to support. Examine a failing image alongside its expected amount and opt-in diagnostics to decide
whether text recognition, row reconstruction, amount selection, or evidence grading caused it.

After a change, rerun the same labelled images with the same runtime and repetition count:

```bash
.venv/bin/python tools/benchmark.py \
  --manifest private-inputs/development-cases.json \
  --repetitions 1 \
  --output output/development-after.json
```

Compare `summary.exact_match_rate`, `summary.false_strong_count`, `summary.error_count`, category
results, and `durations.p95_ms`. Match individual runs by `case_id` and `repetition` to check both
fixed cases and regressions. Repeat runs when investigating timing or inconsistent outcomes; the
reported accuracy then counts every repetition, while `case_count` remains the unique case count.
Keep the input images and labels unchanged during a comparison.

Add synthetic reproductions under `tests/fixtures/` and public-interface assertions in
`tests/test_public_interface.py`, then run the portable and integration suites again. Changes to
preprocessing, OCR pass scheduling, evidence grading, or the runtime baseline need holdout
requalification before release; see [CONTRIBUTING.md](../CONTRIBUTING.md).

## What these results establish

A development benchmark helps discover failures and compare changes on your chosen images. It does
not measure general receipt accuracy or pass the v1 release gate, even under a conformant runtime.
The report always sets `eligible_for_release_gate` to `false`; runtime conformance reporting only
indicates the runtime policy and baseline checks succeeded. Repeated or tuned-on cases are not an
independent holdout.

The release evaluator remains [tools/holdout/evaluate.py](../tools/holdout/evaluate.py), with a
frozen authorized corpus of at least 300 images and 100 per supported app. See the
[holdout process](../tools/holdout/README.md) and [release gate](release/v1-gate.md). Current scope is
INR payable totals from Blinkit, Swiggy, and Zepto images; PDFs, HEIC, handwriting, line-item
extraction, and merchant/date extraction are outside the supported scope.
