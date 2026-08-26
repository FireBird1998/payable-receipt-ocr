# ADR-0007: Private Holdout Evaluation

**Status:** Accepted

## Decision

Accuracy and quality claims are substantiated only by a private holdout corpus. The corpus and its
evaluation report are never committed to this repository or published in CI artifacts.

### Corpus requirements

- At least **300 cases** total.
- At least **100 cases per app** (`blinkit`, `swiggy`, `zepto`).
- Receipts collected only with explicit consent and legal permission from the individuals depicted.
- Ground-truth labels (expected total and currency) created **before** any OCR is run on the image,
  to prevent model-feedback bias.
- At least **10% of cases** double-labelled by independent annotators; disagreements adjudicated
  before the corpus is frozen.
- Exact deduplication by image SHA-256 hash.
- Perceptual deduplication checked manually for near-duplicates.
- Stratified by app and capture type before freeze.

### Corpus freeze and manifest

Each frozen corpus version carries:
- `corpus_version`: opaque version string
- `frozen_at`: ISO-8601 UTC timestamp
- `manifest_sha256`: SHA-256 of the canonicalized manifest JSON (excluding this field)
- `runtime_baseline_id`: the package baseline ID the run is expected to match

Frozen manifests are immutable. Re-running on a new corpus version requires a new freeze with a
new `corpus_version`.

### Gate math

The `tools/holdout/evaluate.py` evaluator computes:

```
exact_match_rate     = cases where (observed_total == expected_total AND currency == "INR") / total_cases
false_strong_count   = cases where evidence_grade == "strong" AND exact_match is False
confirmation_rate    = cases where requires_confirmation == True / total_cases
p95_duration_ms      = 95th-percentile call duration across all cases (nearest-rank method)
```

A run is **eligible** only when:
- `runtime_policy="conformant"` was used
- All cases reported `conformant=True` from the runtime baseline
- All `baseline_id` values matched the manifest's `runtime_baseline_id`
- No cases raised an unhandled error

The holdout **gate passes** when all five conditions hold:
1. Eligible (as above)
2. `exact_match_rate >= 0.95`
3. `false_strong_count == 0`
4. `confirmation_rate == 1.0`
5. `p95_duration_ms < 5000`

### Statistical caveat

A corpus of 300 cases meeting the 95% threshold demonstrates that at least 285 of those 300 cases
were recognized correctly. This is not a proof that the true population error rate is below 5%, nor
does it guarantee zero future false-strong results. The threshold is a necessary gate, not a
sufficient production-readiness proof.

### Privacy

- The evaluation report contains per-case outcome records keyed by opaque `case_id`. No filenames,
  image paths, or OCR text appear in the report.
- Aggregate metrics (rates, p95, warning counts) may be stated publicly.
- Per-case records and the corpus itself remain in private storage under the same controls as the
  receipt images.

### Public claims

Quantitative performance claims in public documentation must:
- State the corpus version and holdout run date.
- Cite aggregate metrics only (rate, count, p95) — never per-case details.
- Clearly distinguish between the exploratory development corpus (not an independent benchmark) and
  a frozen, authorized holdout.

## Why

Pre-OCR labelling prevents the algorithm from being tuned to its own evaluation set. A minimum of
300 cases with 100 per app ensures that a single app's characteristic layout cannot dominate the
pass/fail outcome. Double-labelling 10% provides a check on annotator consistency before the
corpus is frozen. The private-only data requirement prevents any real receipt data from appearing
in public repositories, CI logs, or issue threads.
