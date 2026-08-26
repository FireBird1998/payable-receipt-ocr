# ADR-0001: Runtime Baseline and Model Provisioning

**Status:** Accepted (baseline tuple: candidate — not yet benchmarked on reference environment)

## Decision

No OCR model is downloaded at recognition time. Both `eng.traineddata` and `Devanagari.traineddata`
must be present and checksum-verified before recognition begins. Discovery follows this priority
order:

1. Explicit `tessdata_dir` argument
2. `PAYABLE_RECEIPT_OCR_TESSDATA_DIR` environment variable
3. XDG data home (`$XDG_DATA_HOME/payable-receipt-ocr/tessdata`, defaulting to
   `~/.local/share/payable-receipt-ocr/tessdata`)

If neither model file is found in any candidate directory, `RuntimeBaselineError` is raised
before any OCR is attempted. A checksum mismatch always raises `RuntimeBaselineError` regardless
of `runtime_policy`.

A single baseline tuple is recorded in `runtime-baseline.toml`:

```toml
baseline_id = "linux-noble-amd64-2026-08"
os_name     = "ubuntu-24.04"
arch        = "amd64"
tesseract_first_line = "tesseract 5.3.4"
oem         = 1
psm_allowed = "4,6,11"
omp_thread_limit = "1"

[models]
eng        = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
Devanagari = "3bbb87c1de2a6a2ef0a97dc041e6eea2723a1c22d638f5e38157a5cd441c12b7"
```

Under `runtime_policy="development"`, a mismatch on OS/arch/Tesseract version is recorded in
`RuntimeProvenance.conformant=False` but does not block recognition. Under
`runtime_policy="conformant"`, any such mismatch raises `RuntimeBaselineError`.

The current manifest validates specific fields (model checksums, Tesseract version string, OS,
arch) against the recorded tuple. Reproducibility of recognition output also depends on factors
outside the manifest — such as system locale, Tesseract build flags, and libc version — which are
not currently captured. An immutable, retained instance of the full reference runtime is required
before `conformant` results are meaningful quality evidence.

A change to a pinned model file SHA-256 or to the baseline tuple requires holdout requalification
before the new baseline is released.

## Why

- Preventing runtime downloads eliminates a class of supply-chain and privacy risks: the package
  cannot silently pull a different model mid-run.
- Checksum pinning makes model identity auditable and reproducible.
- Explicit/env/XDG discovery is ordered from most-specific to least-specific, matching standard
  Linux data-home conventions.
- Separating `development` and `conformant` policies allows development on macOS or other Linux
  distributions while preserving a strict gate for evidence-producing runs on the reference
  environment.
