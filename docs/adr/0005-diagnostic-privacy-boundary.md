# ADR-0005: Diagnostic Privacy Boundary

**Status:** Accepted

## Decision

Diagnostics are opt-in at recognition time. The caller must pass `diagnostics=True` to `recognize()`
(or `--diagnostics` on the CLI) to receive the `diagnostics` key in the result.

A result object created **without** `diagnostics=True` does not retain any raw OCR text in memory.
Calling `result.to_dict(include_diagnostics=True)` on a non-diagnostic result raises `ValueError`
rather than returning an incomplete payload.

### What diagnostics contain

When enabled, the `diagnostics` key includes:

- `ocr.passes[].raw_text` — the full concatenated OCR text from each completed pass
- `ocr.passes[].lines` — individual line records with text, confidence, and bounding-box coordinates
- `candidates` — all monetary candidates extracted and their scores
- `candidate_groups` — aggregated candidate groups with cross-pass support detail

This data can contain personal information visible on the receipt: names, addresses, item
descriptions, amounts, merchant text.

### What the package does not do

- The package itself writes no log files and no persistent files during recognition.
- The package makes no network requests.
- The OCR adapter writes a prepared image to a uniquely named file under `TMPDIR`, invokes
  Tesseract with an isolated subprocess environment, and deletes the input in a `finally` block.
  Tesseract may create additional temporary files, and process crashes can prevent normal cleanup.

### Filename sensitivity

`source.filename` is always present in the result (it is the basename of the input path). File
names may carry personal information (e.g. `2026-08-john-doe-zepto.png`). Callers are responsible
for scrubbing filenames before logging or transmitting results.

### No network, no package logging

The package does not call `logging.getLogger` or emit any Python `logging` records. It does not
open sockets, make DNS queries, or contact any remote service.

### Recommendations for sensitive environments

- Use `tmpfs` or an equivalent in-memory filesystem for `TMPDIR` to prevent receipt-derived
  temporary files from touching persistent storage.
- Do not pass `diagnostics=True` in production unless the raw OCR output is handled under the same
  retention and access controls as the receipt image itself.
- Retain private holdout evaluation reports under the same controls as the receipt images.

## Why

Opt-in diagnostics mean that the default path — the one taken by the vast majority of production
calls — never retains or transmits raw OCR text. A caller who needs diagnostics for debugging must
make an explicit decision at the call site. The choice cannot be accidentally inherited from a
default or environment-variable configuration.
