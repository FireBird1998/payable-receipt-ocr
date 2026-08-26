# Architecture

`payable-receipt-ocr` is a single-process, synchronous, stateless library. It reads one image, runs
OCR locally, and returns a typed suggestion. It makes no network requests, spawns no background
threads, and makes no persistent writes during recognition. All concurrency is the caller's
responsibility; prepared images exist only as short-lived system temporary files.

---

## Public seam

Three things are public and stable:

| Surface | Where |
|---|---|
| `recognize(image, *, currency, …)` | `payable_receipt_ocr.recognize` |
| `RecognitionResult` and related types | `payable_receipt_ocr` top-level |
| JSON schema `payable-receipt-ocr/1` | Shared by Python `to_dict()` and the CLI |

Everything else—module names, internal function signatures, intermediate data structures—is private
implementation detail. See [docs/schema/v1.md](docs/schema/v1.md) for the normative contract.

### `recognize`

```python
from payable_receipt_ocr import recognize

result = recognize(
    "zepto-checkout.png",
    currency="INR",  # required; only "INR" is supported in the production scope
    tessdata_dir=None,  # explicit model dir; falls back to env/XDG
    diagnostics=False,  # opt-in; diagnostics contain raw OCR text
    deadline_seconds=5.0,
    pass_timeout_seconds=2.0,
    runtime_policy="development",  # "development" or "conformant"
)
```

It delegates immediately to `_engine.process_receipt` and returns a `RecognitionResult`. Validation
of paths and currency happens in `api.py` before the engine is called.

### `RecognitionResult`

A frozen dataclass. The two invariants that cannot be overridden:

```python
result.requires_confirmation  # always True
result.authorizes_persistence  # always False
```

`result.evidence_grade` is `"strong"`, `"review"`, or `"none"`. Strong evidence means independent
OCR passes agreed—it is not permission to save an expense without showing the result to a person.

---

## Private modules

All internal modules carry a `_` prefix. They are not importable from the public namespace and are
not covered by the schema stability guarantee.

### `_engine` — orchestrator

`process_receipt` is the single entry point for the pipeline. It:

1. Calls `_image.load_source_image` → `_image.prepare_variants`
2. Calls `_runtime.validate_runtime` to discover and checksum-verify models
3. Runs `_ocr.build_schedule(include_adaptive=False, include_rescue=False)` — 4 baseline passes
4. Evaluates the baseline interpretation; if grade is not `"strong"` and time remains, runs the
   remaining adaptive/rescue passes (up to 12 total)
5. Calls `_interpretation.interpret` on the completed passes
6. Assembles the raw `dict` payload that `RecognitionResult.from_payload` deserializes

The engine sets `max_workers=1`; it does not use thread or process pools. Service-level
concurrency is the caller's responsibility.

### `_image` — image loading and preprocessing

Enforces the input envelope: 10 MiB file, 12 megapixel decoded source. Applies EXIF orientation
correction via Pillow, then deskews via Hough line detection, normalizes contrast, and creates two
image variants for OCR:

- `normalized-grayscale`: contrast-normalized grayscale with 24 px white padding
- `adaptive-threshold`: Gaussian adaptive-threshold binarization with 24 px white padding

Both are scaled to fit within 1 600 px wide, 2 600 px on the longest side, and 4.5 MP.

### `_ocr` — OCR scheduling and execution

`build_schedule` builds an ordered list of `PlannedPass(variant, language, psm)` tuples. The
baseline schedule is:

```
normalized-grayscale × {eng, Devanagari} × {psm 6, psm 4}   = 4 passes
```

If the baseline grade is not `"strong"`, the remainder is scheduled:

```
adaptive-threshold    × {eng, Devanagari} × {psm 6, psm 4}   = 4 more
normalized-grayscale  × {eng, Devanagari} × {psm 11}          = 2 more
adaptive-threshold    × {eng, Devanagari} × {psm 11}          = 2 more
                                                    total ≤ 12 passes
```

Each pass is executed sequentially under a per-pass timeout (`pass_timeout_seconds`) and a global
deadline (`deadline_seconds`). The Tesseract subprocess receives an isolated environment with
`OMP_THREAD_LIMIT=1`; the caller's process environment is not mutated.

The OCR adapter writes a prepared variant to a uniquely named PNG under `TMPDIR`, calls the local
Tesseract executable directly, parses TSV output, and deletes the PNG in a `finally` block.
Tesseract may create additional system temporary files.

### `_interpretation` — candidate ranking and evidence grading

Receives the completed `OcrPassResult` tuples. For each pass and line, extracts monetary candidates,
classifies lines as payment labels, fallback totals, component amounts, or unlabeled, and scores
each candidate. After aggregating cross-pass support, `_evidence_grade` applies the strict
corroboration policy:

`"strong"` requires **all** of:
- `label_kind == "payment"` (a recognized payment label)
- No competing total with equal or greater support
- At least one explicit INR currency marker
- Not degraded (no failed passes, no deadline pressure)
- No `ranking_warning`, `currency_conflict`, or `competing_total` warning codes
- Either: passes from ≥ 2 languages with ≥ 3 total passes, **or** arithmetic corroboration from ≥ 2
  passes (component amounts sum to the total within tolerance)

Any degradation (failed pass or deadline exceeded) caps the grade at `"review"`.

### `_runtime` — model discovery and baseline validation

Implements the three-tier tessdata discovery: explicit `tessdata_dir` argument → `PAYABLE_RECEIPT_OCR_TESSDATA_DIR`
environment variable → XDG data home (`~/.local/share/payable-receipt-ocr/tessdata`). Once
resolved, it checksums `eng.traineddata` and `Devanagari.traineddata` against the pinned values in
`runtime-baseline.toml`. A mismatch always raises `RuntimeBaselineError`.

The module additionally checks whether the running OS, architecture, and Tesseract version string
match the baseline tuple:

- `runtime_policy="development"` (default): logs the drift in `RuntimeProvenance.conformant=False`
  and continues.
- `runtime_policy="conformant"`: raises `RuntimeBaselineError` if any tuple field differs.

Model checksums are validated on every call; the baseline OS/arch/version check sets `conformant`
but only blocks in conformant policy mode. The current baseline tuple is:

```
baseline_id = "linux-noble-amd64-2026-08"
os_name     = "ubuntu-24.04"
arch        = "amd64"
tesseract   = "tesseract 5.3.4"
```

This tuple is the **candidate** conformance target. Benchmark results on this exact retained
runtime are required before `conformant` becomes a meaningful quality signal. macOS is a supported
development environment but is not the conformance target.

### `_contracts` — typed frozen records

Defines the private internal types (`SourceImage`, `PreparedVariant`, `OcrLine`, `OcrPassResult`,
`InterpretationResult`, `Candidate`, `CandidateGroup`, `RuntimeBaseline`, `RuntimeValidation`,
etc.). These are frozen dataclasses. They are the seams between pipeline stages.

---

## Call direction

```
recognize()               [api.py – public]
  └─► process_receipt()   [_engine.py – private orchestrator]
        ├─► load_source_image / prepare_variants   [_image.py]
        ├─► validate_runtime                        [_runtime.py]
        ├─► build_schedule / execute_schedule       [_ocr.py]
        └─► interpret                               [_interpretation.py]
              └─ uses typed records from            [_contracts.py]
```

The CLI (`cli.py`) is a thin adapter that calls `recognize()` and serializes `result.to_dict()` to
stdout as compact JSON.

---

## Why there is no public provider plugin

The package has no plugin interface for OCR engines or currency providers. Tesseract is the only
OCR backend. INR is the only production-scope currency. A plugin system would widen the trust
boundary, complicate the holdout reproducibility contract, and add integration-test surface without
a concrete use case.

---

## Stateless, local, synchronous

- **No state between calls.** Each `recognize()` call is independent. There is no cache, session,
  or connection pool.
- **No network.** The library performs no HTTP, DNS, or socket operations.
- **No persistent writes.** Prepared variants are deleted from `TMPDIR` after each pass. Process
  crashes can prevent normal cleanup, and Tesseract may create additional temporary files.
- **Synchronous.** `recognize()` blocks the calling thread until it returns. The service layer is
  responsible for running multiple recognitions concurrently.

---

## Diagnostics and privacy

`diagnostics=False` by default. When enabled, the result's `diagnostics` key contains raw OCR
text from every completed pass and the full ranked candidate list. This data can include personal
information visible on the receipt (amounts, labels, merchant text). Diagnostics are opt-in at
call time; the result object does not retain them unless `diagnostics=True` was passed to
`recognize()`. See [SECURITY.md](SECURITY.md) and
[ADR-0005](docs/adr/0005-diagnostic-privacy-boundary.md).

---

## Development runtime vs. Linux conformance

The package distinguishes two runtime stances:

| Policy | Behavior on baseline mismatch |
|---|---|
| `"development"` (default) | Continues; sets `conformant=False` in the result |
| `"conformant"` | Raises `RuntimeBaselineError` |

macOS is used for development and passes the unit and integration test suite. All holdout
evaluation and performance benchmarking is done on the retained reference runtime
(`ubuntu-24.04 / amd64 / tesseract 5.3.4`). Latency figures, the p95 deadline claim, and the
memory ceiling are only meaningful when measured on that retained tuple; no such measurement has
been completed. See [ADR-0001](docs/adr/0001-runtime-baseline-and-model-provisioning.md) and
[docs/release/v1-gate.md](docs/release/v1-gate.md).
