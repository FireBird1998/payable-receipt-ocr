# v1 Release Gate

This checklist must be completed before the version is bumped from `0.x.y` alpha to `1.0.0`. Every
item marked `[ ]` is currently unproven or unmet.

Items marked `[x]` have been implemented in the codebase. Implementation alone does not constitute
meeting the gate — each item specifies what is required.

---

## Corpus and accuracy gate

- [ ] **Frozen private holdout corpus authorized.** At least 300 cases total, at least 100 per
  app (`blinkit`, `swiggy`, `zepto`). Corpus frozen with `corpus_version`, `frozen_at`, and
  `manifest_sha256`. All images collected with explicit consent.
- [ ] **Pre-OCR labels verified.** Ground-truth labels created before any OCR run. At least 10% of
  cases double-labelled; all adjudication complete.
- [ ] **Image deduplication complete.** SHA-256 exact deduplication run; perceptual near-duplicate
  review complete.
- [ ] **Exact total + currency ≥ 95%.** `exact_match_rate >= 0.95` on the authorized frozen
  corpus, measured under `runtime_policy="conformant"` on the retained reference runtime.
- [ ] **False-strong count = 0.** Zero cases where `evidence_grade == "strong"` and
  `total + currency` is incorrect.
- [ ] **Confirmation rate = 100%.** Every result has `requires_confirmation=True`. This is
  currently enforced by code but must be confirmed in the holdout run.

---

## Runtime and performance gate

- [ ] **Retained reference runtime available.** An immutable, retained instance of
  `ubuntu-24.04 / amd64 / tesseract 5.3.4` (baseline `linux-noble-amd64-2026-08`) is provisioned
  and locked for the conformant holdout run.
- [ ] **p95 latency < 5 000 ms measured.** p95 call duration measured on the retained reference
  runtime across all holdout cases; confirmed < 5 000 ms.
- [ ] **600 MiB memory ceiling measured.** Peak per-process memory measured on the reference
  runtime during the holdout run; confirmed ≤ 600 MiB.
- [ ] **Deterministic repeat probe.** The same image run twice consecutively on the reference
  runtime produces identical `total`, `currency`, `evidence_grade`, and `matched_label`.
- [ ] **Model and runtime SHA-256 hashes recorded.** `eng.traineddata` and
  `Devanagari.traineddata` checksums in `runtime-baseline.toml` match the hashes measured during
  the holdout run. Tesseract version string confirmed.

---

## CI gate

- [x] **Portable tests green.** `pytest -m 'not integration'` passes on the current commit. These
  tests require no Tesseract installation.
- [ ] **Integration tests green.** `pytest -m integration` passes with Tesseract installed and
  models provisioned.
- [ ] **Conformance CI pipeline green.** CI run on the retained reference runtime with
  `runtime_policy="conformant"` passes all tests.
- [x] **Package build and twine check pass.** `python -m build && twine check dist/*` succeeds.
- [x] **Artifact privacy scan green.** `tools/check_artifacts.py` reports no receipt images, OCR
  dumps, or private data in the build artifacts.

---

## Privacy and security gate

- [ ] **Privacy review complete.** A documented review confirms: no real receipt data in the
  repository, diagnostics default to off, `source.filename` handling documented, Tesseract temp-
  file behavior documented, no network requests, no package-level logging.
- [ ] **Security review complete.** A documented review of input validation (file-size cap, pixel
  cap, format allowlist), error message content, and dependency versions.
- [ ] **No private data in public repository.** Confirmed: no holdout images, OCR text, or
  per-case labels appear in git history, CI artifacts, GitHub Actions logs, or published docs.

---

## Documentation and migration gate

- [x] **Schema reference published.** `docs/schema/v1.md` describes the `payable-receipt-ocr/1`
  contract, migration from the old alpha schema, and all field meanings.
- [x] **Architecture documented.** `ARCHITECTURE.md` describes the public seam, private modules,
  call direction, and the development vs. conformance distinction.
- [x] **ADRs complete.** ADRs 0001–0008 cover all major decisions.
- [ ] **Migration notes verified.** Consumers of the old alpha schema can follow the migration
  guide in `docs/schema/v1.md` to update their code; at least one consumer has been tested.
- [ ] **README updated for v1.** All stale fields, gate numbers, and schema examples corrected.

---

## Supported environment and non-guarantees

The v1 conformance environment is `ubuntu-24.04 / amd64 / tesseract 5.3.4` with the pinned model
files. Other configurations (other Linux distributions, macOS, ARM, other Tesseract versions) are
supported for development and will produce results, but are not the conformance target and are not
covered by the accuracy gate.

- macOS is a supported **development** environment, not a conformance environment.
- INR is the only production-scope currency in v1.
- The package does not support PDFs, HEIC, handwriting, multipage documents, line-item extraction,
  or any server mode.

---

## Statistical caveat

Passing the holdout gate (≥ 95% exact on ≥ 300 cases, 0 false-strong) establishes that the
algorithm met the threshold on a specific frozen corpus under a specific retained runtime. It is
**not** a proof that:
- The true population error rate is below 5%.
- Future images from the same apps will not produce false-strong results.
- Performance will be identical on different runtime environments.

The gate is a necessary condition for v1, not a sufficient proof of production-readiness.
