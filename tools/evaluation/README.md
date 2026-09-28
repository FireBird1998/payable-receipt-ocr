# Expansion evaluation protocol

Developer-only tooling for [ticket #14](https://github.com/FireBird1998/payable-receipt-ocr/issues/14).
It freezes labels and scores recorded observations; it does not run OCR, replace the
existing holdout gate, or declare release qualification. The three-engine runner is
separate work. Real manifests, observations and detailed reports stay in ignored
private storage. Only the supplied synthetic example may be committed.

## Reproducible synthetic check

From the repository root in the development virtual environment:

```sh
python tools/evaluation/protocol.py validate tools/evaluation/example/manifest.json --corpus tools/evaluation/example
python tools/evaluation/protocol.py score tools/evaluation/example/manifest.json --observations tools/evaluation/example/observations.json --output output/synthetic-protocol-report.json
pytest tests/test_evaluation_protocol.py
```

Create `output/` if needed. Output files are exclusive: use a fresh name for each
run; an existing file is never replaced. The four images are generated synthetic
bills and the twelve observations are simulated, including a wrong-field zero and
a failed call. Their timings, candidate identity and hardware are explicitly fictional.
Expect two numeric payable matches but one evidence-correct match, one correct
negative control out of two, a 9,000 ms p95 including failures, four independent
images and twelve calls. No OCR accuracy or hardware claim follows from this replay.

## Frozen label contract

The executable validator is `protocol.py`; `example/manifest.json` is the complete
versioned example. All monetary amounts are canonical two-decimal strings, including
`0.00`; absence is null, never zero. Top-level fields:

| Field | Requirement |
| --- | --- |
| `schema` | `payable-ocr-evaluation/1` |
| `policy_version` | `india-payable/1` |
| `corpus_version` | New immutable identity for each freeze |
| `frozen_at` | ISO-8601 UTC timestamp |
| `historical_manifests` | Array of retained version and byte SHA-256; empty for a fresh unrelated corpus |
| `manifest_sha256` | SHA-256 of sorted compact UTF-8 JSON excluding this field; default JSON ASCII escaping |
| `cases` | Nonempty unique cases, described below |

Each case requires opaque `id`, relative `image`, image SHA-256, original `width`
and `height`, `family`, `language` (`en`, `hi`, `mixed`), capture type, provenance,
`split`, `transaction_group`, `near_duplicate_group`, and an opaque `label_reference`.
Families are the existing three apps plus restaurant, retail, pharmacy, fuel,
transport (including toll) and utility. Capture types are screenshot, photo and
pdf-render; this does not add PDF support to the library. Provenance is synthetic,
vendor-sample, public-bill, unknown-example or authorized-receipt. Qualification
requires authorized-receipt provenance, `unseen: true` and an opaque authorization
reference. These declarations support an independent audit; they cannot prove consent.

`expected` contains `total`, `currency`, `role`, `source_region`, `negative_reason`.
A payable label has INR, `final-payable`, a nonempty original-image box `[x1,y1,x2,y2]`
and no negative reason. Boxes surround the amount/NIL field, not the whole receipt.
Coordinates use a top-left origin and exclusive right/bottom boundaries. Negative
controls have null amount/currency/box, `no-payable`, and one of `missing-total`,
`ambiguous-due-date`, `ambiguous-partial-payment`, `credit`, `non-payable`.

Optional `historical_expected` records the old total/currency and the retained
manifest SHA-256. Thus a chosen before-due amount can remain a historical numeric
pass while `india-payable/1` requires abstention. Never edit an earlier manifest or
copy an old label into a new policy without adjudication. Source-region annotations
for real bills must be completed independently before freezing changed-engine inputs.

To freeze a draft, omit `manifest_sha256` and run:

```sh
python tools/evaluation/protocol.py freeze private-inputs/new-policy-draft.json --corpus private-inputs/corpus --output private-inputs/new-policy-frozen.json
```

Freeze/validate verify image bytes, dimensions and containment including symlinks.
Exact duplicates are rejected. Transaction and near-duplicate groups cannot cross
splits, and correlated qualification images are rejected even in the same split.
Development variants may share groups; report their correlation and do not claim
that per-image development metrics measure independent population samples.

## Observation contract and metrics

Use `payable-ocr-observations/1`, the frozen manifest hash, one candidate provenance
record and `runs`. Candidate provenance requires engine/version, a code commit,
model hashes, explicit settings, and environment OS/architecture/CPU/RAM/core count.
A reference environment must identify a retained, non-emulated Ubuntu 24.04 amd64
host. Record detector, recognizer, dictionaries, preprocessing, routing, threading,
package versions and inference backend in model hashes/settings before actual runs.
Compare all candidates on this same hardware and frozen manifest. Never serialize a
Paddle result as the Tesseract public v1 contract.

Every run records `case_id`, zero-based `repetition`, total/currency, grade, original-
image `source_region` and adjudicable `source_role`, error (`controlled`, `unexpected`
or null), full-call duration, initialization time, process/process-tree peak MiB,
confirmation and persistence flags. Unknown resource measurements are null, not zero.
Errors contain no suggestion; error confirmation flags may be null. All case/repetition
pairs must be present exactly once with the same contiguous repetitions for each case.
Source regions must describe the actual selected evidence, not copy ground truth.

| Metric | Numerator / denominator |
| --- | --- |
| Primary exact payable rate | Correct amount+currency / stated-payable images, first repetition only |
| Evidence-correct payable rate | Exact matches with final-payable role and source-box IoU ≥ 0.5 / stated-payable images |
| Negative-control rate | Successful null suggestions / negative controls; errors are failures |
| Wrong suggestions | Non-null suggestions that mismatch policy target, including negative controls |
| Abstentions | Successful null suggestions; excludes execution errors |
| False-strong | Strong suggestions with wrong amount/currency or a negative-control target |
| Strong wrong field | Numerically exact strong suggestions with located but incorrect payable evidence |
| Strong unlocated | Numerically exact strong suggestions lacking source evidence; never evidence-correct |
| Confirmation rate | Confirmation-required returned results / returned results; errors reported separately |
| Persistence violations | Any run authorizing persistence, including an erroneous run |
| Strong coverage | Strong results / returned results |
| Error rate | Failed calls / all calls in the selected cohort |
| Historical matches | Exact matches against separately retained historical labels; not new-policy successes |
| Latency p50/p95/p99 | Nearest rank over all calls, including errors, deadlines and initialization incurred by calls |
| Resource maxima | Maximum over measured calls, with measurement count; null if unmeasured |

`primary` uses repetition zero; `all_calls` exposes every error/safety violation.
Stability includes amount, currency, grade, error, source evidence and confirmation
flags. Reports include family, language, family/language, capture, split and provenance
cohorts. No per-case source paths, OCR text or expected amounts are emitted by the
scorer, but full reports/candidate metadata still remain private for real datasets.
The tool is a replay check, not an independent judge of an adapter's source claims;
manual label adjudication and trusted observation collection remain required.

## Retain unchanged Tesseract and historical files

The anchor is `af7c5e4d0593a6354feebbd0bbbe0c8d687d01a3`.
`historical-runtime.json` records verified model hashes, the observed development
runtime and unchanged default settings. Reference runtime constraints remain the
existing package baseline. No engine/configuration B or C has been implemented or
silently substituted for A.

```sh
python tools/evaluation/retain_baseline.py --output output/retained-baseline-v1 --manifest private-inputs/india-bills-2026-09-28/cases.json --manifest private-inputs/india-bills-round2-2026-09-28/cases.json
```

Use actual historical manifest paths and a new output directory. This saves an exact
source archive and byte-identical historical manifests with hashes, without changing
originals. The retention record contains private paths and must stay private. Failed
retention may leave a partial new directory; only a completed `retention.json` proves
completion. Never repurpose a partial directory as a completed freeze.

To replay A, unpack the retained source archive into a new private directory, create
an isolated environment there, install that source and the retained dependency
versions, provision the already pinned models, and invoke:

```sh
python tools/benchmark.py --manifest /absolute/path/to/historical-cases.json --repetitions 3 --runtime-policy development --output /absolute/path/to/new-baseline-report.json
```

Use the original manifest in its original location because legacy image paths are
relative to it; verify its hash against retention first. Saved manifest copies are
for byte preservation, not relocated invocations. Keep old reports unchanged.
Development replay uses the captured Python/Tesseract/native-library versions as
well as the model hashes; package pinning alone is not binary reproducibility.
For Linux qualification use the pinned conformant runtime and a registered reference
host. The current ARM64 desktop/Docker pair is not that host.

## Open prerequisite

The retained Linux amd64 hardware is **unregistered**. Record its CPU model, allocated
logical CPUs, RAM, OS, host identity and lack of emulation before any comparative
qualification run. Lock A/B/C configuration and all dependency/model hashes before
exposing a new authorized holdout. This tool deliberately always reports
`release_qualification: false`; ticket #23 implements the later complete gate.

## Local Docker development and testing

Docker is sufficient for local Linux development, regression tests and explicitly
labelled exploratory comparisons. A dedicated amd64 machine is not a prerequisite
for continuing those tasks. From the repository root:

```sh
bash tools/evaluation/docker/run.sh
bash tools/evaluation/docker/run.sh python -m payable_receipt_ocr tests/fixtures/clean-screenshot.png --runtime-policy development
```

The helper builds for Docker's native architecture, then runs with networking disabled,
two CPU cores of quota, 2 GiB memory, a read-only root filesystem and a temporary
writable `/tmp`. Override quotas with `OCR_DOCKER_CPUS` and `OCR_DOCKER_MEMORY` and
record those values with every comparison. Do not confuse the container's 2 GiB cap
with the proposed 600 MiB per-process release target.

The Ubuntu 24.04 base image is digest-pinned, Tesseract is pinned to 5.3.4-1build5,
Python numerical/image/test packages are pinned, and OCR models are checksum-verified
during build. The build allowlist includes source and synthetic fixtures; private
inputs, historical snapshots, `.git`, credentials and local environments are excluded.
Provisioning uses the network only during build. Receipt recognition runs offline.
The image records resolved Python and OS packages in `/opt/python-packages.txt` and
`/opt/os-packages.txt`. Retain its image ID and export it before treating a run as a
frozen baseline; unpinned transitive apt/build dependencies can change on rebuild.

```sh
docker image inspect payable-ocr-dev:arm64 --format '{{.Id}}'
docker save payable-ocr-dev:arm64 --output output/ocr-dev-arm64-image.tar
```

On this Apple Silicon machine, native Docker is Linux ARM64. An optional
`OCR_DOCKER_PLATFORM=linux/amd64` build/run uses emulation here; it can exercise amd64
compatibility but does not establish native-amd64 latency or memory performance.
Record the host architecture and whether emulation was used outside the container;
`uname -m` inside an emulated container is not proof of native hardware.
[Docker documents these architecture and emulation constraints](https://docs.docker.com/build/building/multi-platform/).
A future ARM64 release baseline is possible through a deliberate runtime decision and
fresh qualification; the current amd64 release claim remains governed by the ADRs.
