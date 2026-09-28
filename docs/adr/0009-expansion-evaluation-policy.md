# ADR-0009: Expansion evaluation policy and immutable comparisons

**Status:** Accepted for development evaluation; retained reference hardware is not yet registered.

Indian bill expansion needs a versioned payable policy and field evidence: inspected
examples showed that a numerically correct zero can come from the wrong field. Compare
unchanged Tesseract, repaired Tesseract and PaddleOCR against the same frozen labels;
preserve historical expectations separately instead of changing them after seeing results.
This follows the approved [expansion specification](https://github.com/FireBird1998/payable-receipt-ocr/issues/13).

## Decision

Use `india-payable/1`: an unambiguous printed final payable is the target, explicit
final NIL/zero is valid, and ambiguous due-date windows, partial-payment targets,
credits without a unique nonnegative payable, and missing totals require abstention.
Arithmetic must not manufacture a missing payable or silently replace a printed one.

Freeze case provenance, script/family, source regions and transaction/near-duplicate
groups before running changed engines. Frozen manifests are content-hashed and immutable;
a policy change creates a new version linked to retained historical manifests. Exact
image duplicates are rejected. Related images cannot cross development/qualification
splits; qualification admits at most one image per transaction or near-duplicate group.

Score exact amount/currency separately from evidence-correct extraction. Evidence must
identify the final payable role and overlap the adjudicated original-image field box
with intersection-over-union at least 0.5. This predeclared localization threshold is
an evaluation convention, not proof that arbitrary OCR text is semantically correct.
Annotators review the payable role and box before freeze; adapters cannot self-label
an amount as correct. Missing localization is unverified evidence, not a correct field.

First repetitions provide the primary per-image result. All repetitions are separately
reported for stability, errors, false-strong and confirmation violations; failures stay
in latency denominators. Negative controls have their own denominators. Never multiply
sample size by repetition count. Report capture, provenance, script and family/script
cohorts separately. The replay scorer does not authorize a release.

## Qualification requirements retained and added

ADR-0007's 300 authorized unseen images, at least 100 per existing delivery app,
and ADR-0008's full release gate remain intact. Additionally, each new family needs
at least 50 authorized unseen stated-payable images, at least 20 in each declared
language cohort within that family, and at least 95% exact and evidence-correct matches
per declared cohort. Mixed-script coverage is separate. At least 20 negative controls
must all abstain correctly. Double-label every zero/negative/ambiguous case and at
least 10% elsewhere; adjudicate before freeze. These are project acceptance targets,
not population-wide statistical guarantees.

Require zero false-strong and wrong-field strong results, 100% confirmation-required
results and no persistence authorization. Report strong coverage and unlocated strong
results; lack of evidence cannot pass the evidence gate. Retain candidate p95 below
five seconds and 600 MiB per-process limits on one retained native Ubuntu 24.04 amd64
CPU host, including initialization incurred by each call and separately reporting
process-tree memory. Pin every candidate's code, models, configuration and hardware
before comparison. Changing them after holdout exposure requires fresh qualification.

The available development host is macOS ARM64 and local Docker is Linux ARM64. No
retained amd64 CPU model, core allocation or RAM allocation has been identified.
Registration remains an explicit prerequisite; neither development timings nor a
synthetic replay can substitute for it. This decision adds no engine, changes no
recognition defaults, and does not override the public schema or existing runtime ADRs.
