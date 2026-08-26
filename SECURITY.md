# Security policy

## Supported version

Only the latest alpha release receives fixes while the project is below `1.0`.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a public issue with
private receipt content, OCR text, credentials, or exploit details.

## Receipt privacy

### Call-time diagnostics

Diagnostic output is disabled by default. It is enabled only when the caller passes
`diagnostics=True` to `recognize()` or `--diagnostics` on the CLI. When enabled, the result's
`diagnostics` key contains the full recognized receipt text from every completed OCR pass, line-
level bounding boxes, and the ranked candidate list. This data can contain names, amounts, and
other personal information visible on the receipt.

A result object produced without `diagnostics=True` retains no raw OCR text. Calling
`to_dict(include_diagnostics=True)` on such a result raises `ValueError` rather than returning an
incomplete payload.

### System temporary files

The package writes each prepared OCR variant to a uniquely named PNG in the system temporary
directory (`TMPDIR`) before invoking Tesseract, then deletes it in a `finally` block. Tesseract may
also create its own temporary files. A process crash can prevent normal cleanup, so environments
where receipt-derived temporary files must not touch persistent storage should point `TMPDIR` at a
`tmpfs` or equivalent in-memory filesystem.

### No logs, no network

The package does not emit Python `logging` records and does not open sockets or make DNS queries.
No OCR text, candidate data, or receipt content is written to any log or transmitted to any
service.

### Filename sensitivity

`source.filename` in the result is the basename of the input image path. File names that contain
personal information (for example `2026-08-user-name-blinkit.png`) should be scrubbed or replaced
before the result is logged, stored, or transmitted.

### Private holdout data

The private holdout corpus and its evaluation reports are stored in private repositories only. They
must not appear in the public git repository, CI artifacts, GitHub Actions logs, or published
documentation. Private reports may contain opaque case IDs with expected and observed totals,
grades, warning codes, and durations so failures can be audited. They never contain image
filenames, paths, image bytes, or OCR text; only aggregate metrics may be published.

### Callers' responsibilities

Callers remain responsible for upload authentication, temporary-file deletion, resource limits,
log redaction, and retention policies. The package produces an in-process result object; how that
result is stored, logged, or displayed is outside the package's scope.
