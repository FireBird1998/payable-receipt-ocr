# ADR-0006: Private Pipeline Seams

**Status:** Accepted

## Decision

All pipeline stages communicate through typed frozen dataclasses defined in `_contracts.py`. The
stages are:

```
SourceImage  →  PreparedVariant[]  →  OcrPassResult[]  →  InterpretationResult
```

Each record is frozen (immutable after creation) and carries only the data that the next stage
requires. No mutable shared state passes between stages.

### No monolithic second CLI or report command

There is one CLI entry point (`payable-receipt-ocr`) and one public function (`recognize()`).
There is no separate report-generation command, no second binary, and no public CLI subcommand for
pipeline internals. Diagnostic output is accessible only through the `--diagnostics` flag on the
same entry point.

### No public plugin interface

There is no plugin protocol for OCR engines, currency extractors, or scoring strategies. The
pipeline stages are private modules with `_` prefix. Third-party code can call `recognize()` and
receive a `RecognitionResult`; it cannot inject custom OCR backends or interpretation logic.

## Why

Typed frozen records make each stage independently testable and prevent downstream stages from
mutating upstream data. Removing a second CLI / report command eliminated ambiguity about which
surface is the stable contract. A plugin interface would widen the trust boundary without a current
use case and would complicate the holdout reproducibility requirement.
