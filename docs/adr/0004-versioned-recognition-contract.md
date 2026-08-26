# ADR-0004: Versioned Recognition Contract

**Status:** Accepted

## Decision

The Python `to_dict()` method and the CLI JSON output share a single schema identified by:

```
"schema_version": "payable-receipt-ocr/1"
```

This schema is normatively documented in [docs/schema/v1.md](../schema/v1.md).

### Key type choices

- `result.total` is serialized as a decimal string (e.g. `"289.86"`) using Python's `Decimal`,
  quantized to two decimal places. It is `null` when `evidence_grade="none"`.
- `result.currency` is a nullable string (`"INR"` or `null` when `evidence_grade="none"`).
- Monetary amounts use `Decimal`/string to avoid IEEE 754 rounding surprises in downstream
  consumers.

### Warning shape

Warnings are an array of objects:

```json
[{"code": "weak_evidence", "message": "..."}]
```

Warning `code` values are stable identifiers. The `message` is human-readable and may change
across versions.

### Schema sections

Every result contains: `schema_version`, `source`, `processing`, `runtime`, `result`, `warnings`.
`diagnostics` is present only when `diagnostics=True` was passed to `recognize()`.

### Error and exit codes

| Error class | Python code | CLI exit |
|---|---|---|
| `InputFileError` | `input_file` | 3 |
| `UnsupportedImageError` | `unsupported_image` | 4 |
| `ConfigurationError` / `RuntimeBaselineError` | `configuration` / `runtime_baseline` | 5 |
| `OcrEngineError` | `ocr_engine` | 6 |
| Unexpected error | — | 1 |
| Success | — | 0 |

### Pre-v1 migration

The old alpha schema (`payable-receipt-ocr/v1`) differed in several ways:

| Old field | New field / note |
|---|---|
| `"schema_version": "payable-receipt-ocr/v1"` | `"payable-receipt-ocr/1"` — note: no `v` |
| `result.needs_review` | Removed from JSON; `needs_review` property still available on `RecognitionResult` Python object for backward compatibility |
| `result.matched_line` | Removed entirely |
| `warnings` was a string array | Now an array of `{"code": "…", "message": "…"}` objects |
| `pass_count` in `result` | Moved to `processing.passes_completed`; `pass_count` property still on Python object |

### Post-v1 policy

After v1 is released, additive changes (new optional fields, new warning codes) are allowed
without a schema version bump. Removals and type changes to existing fields require a new version.
Consumers should ignore unknown fields to remain forward-compatible.

### No grade authorizes persistence

No evidence grade — including `"strong"` — authorizes an expense to be persisted without
human confirmation. This is not a schema property; it is a domain invariant enforced by the fixed
values `requires_confirmation=True` and `authorizes_persistence=False`.

## Why

A shared Python/CLI schema removes the risk of the two surfaces drifting out of sync. Using a
string decimal for money avoids floating-point errors that would produce incorrect amounts in
downstream JSON consumers. Structured warning objects (code + message) allow consumers to
react programmatically to specific conditions without parsing the message string.
