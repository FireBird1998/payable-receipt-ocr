# ADR-0002: Per-Receipt Resource Envelope

**Status:** Accepted (p95 latency and memory ceiling are candidate values — not yet measured)

## Decision

Each `recognize()` call is bounded by the following hard limits, enforced before or during
recognition:

| Limit | Value | Enforcement point |
|---|---|---|
| Input file size | 10 MiB | `_image.load_source_image` |
| Decoded source pixels | 12 megapixels | `_image.load_source_image` |
| Processed width | ≤ 1 600 px | `_image.prepare_variants` |
| Processed longest side | ≤ 2 600 px | `_image.prepare_variants` |
| Processed pixel area | ≤ 4.5 MP | `_image.prepare_variants` |
| Total call deadline | 5 s (`deadline_seconds=5.0`) | `_engine.process_receipt` |
| Per-pass timeout | 2 s (`pass_timeout_seconds=2.0`) | `_ocr.execute_schedule` |
| OCR worker threads | 1 (`OMP_THREAD_LIMIT=1`) | `_ocr._run_pass` |
| Intra-process concurrency | 1 (`max_workers=1`) | `_engine.process_receipt` |

The engine runs passes sequentially. `max_workers=1` is recorded in the result payload. Service-
level concurrency — running multiple recognition calls in parallel processes or threads — is the
caller's responsibility.

**Candidate p95 latency:** < 5 000 ms on the retained reference runtime
(`ubuntu-24.04 / amd64 / tesseract 5.3.4`). This is the holdout gate threshold. The actual p95
has not yet been measured on the reference environment.

**Candidate memory ceiling:** 600 MiB per-process. This ceiling requires measurement on the
reference runtime before it can be stated as a guarantee.

## Why

- A hard file-size cap prevents the process from being asked to decompress malicious or extremely
  large images.
- A decoded-pixel cap bounds the maximum memory consumed by the source image array.
- The processed-dimension envelope ensures OCR passes run within a consistent time budget
  regardless of source resolution.
- A 5 s total deadline with 2 s per-pass timeout makes the library usable from a synchronous API
  handler without an additional wrapper timeout.
- `OMP_THREAD_LIMIT=1` prevents Tesseract from spawning multiple threads inside a service that
  already manages concurrency at the process level, avoiding oversubscription.
