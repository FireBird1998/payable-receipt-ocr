# Ticket 15: Docker development comparison

The TSV and bounded-row repair was compared with the retained unchanged engine on 74 byte-distinct
existing development images. Historical labels were kept unchanged. These are amount/currency
comparisons, not `india-payable/1` field-localization scores or release qualification.

| Existing corpus | Baseline amount matches | Repaired amount matches | Baseline negative controls | Repaired negative controls |
|---|---:|---:|---:|---:|
| Delivery screenshots, first set | 15/15 | 15/15 | — | — |
| Delivery screenshots, newer set | 17/20 | 18/20 | — | — |
| Other Indian bills, first set | 3/21 | 3/21 | 0/1 | 0/1 |
| Other Indian bills, second set | 2/15 | 2/15 | 2/2 | 2/2 |
| **Total** | **37/71** | **38/71** | **2/3** | **2/3** |

## Repeatability check

Only one image changed exact-match status in the primary comparison. On three additional runs
of that image per engine, both engines matched the expected amount 3/3 times, always at review
grade. The initial baseline call completed six passes, whereas the initial repaired call and
all six rechecks completed eight; deadline variation is a confounder. The initial one-case
gain is **not an established accuracy improvement**. Keep the original first-run scores above
and these six follow-up calls separate; do not select the best run or inflate the image count.

The structural repairs are demonstrated by the controlled public-interface regressions. This
small development comparison found no exact-match regressions, but does not establish a
repeatable real-corpus accuracy gain or readiness for broader bills.

## Safety and scope

| Measure | Baseline | Repaired |
|---|---:|---:|
| Incorrect strong suggestions against historical labels | 0 | 0 |
| Recognition errors | 2 | 2 |
| Confirmation / persistence invariant violations | 0 | 0 |
| Degraded calls | 36 | 33 |
| Deadline reached | 34 | 28 |

A numerically correct result can still come from the wrong field. These historical labels do not
establish field correctness, including for zero values. Remaining semantic errors and missing
localization are covered by the spatial-evidence and payable-policy tickets; this repair changes
neither the default engine nor the mandatory confirmation requirement.

## Reproduction and validation

- One measured repetition per image and engine, all images included, one engine at a time.
- Linux ARM64 Docker with 2 CPU quota, 2 GiB memory cap, read-only root, temporary `/tmp`, network disabled.
- Byte-identical models and identical Python/OS package inventories, default five-second recognition budget and two-second pass timeout.
- Baseline recognition source: `af7c5e4d0593a6354feebbd0bbbe0c8d687d01a3`; Docker runner parent `a581cb0` has identical `src/`.
- Repaired recognition source: `5ac1092`.
- Full native and Docker suites: 105 passed each; 21 synthetic public-interface ingestion regressions, 18 failing before repair.
- Ruff lint/format, build, artifact privacy inspection, Twine, and all five GitHub CI jobs passed.
- Per-image reports, image IDs and manifest hashes are retained locally in ignored `output/ticket15-comparison-2026-09-28/`.

Runtime quotas do not reserve physical CPU cores. One run per image cannot establish timing or
repeatability guarantees; these results do not replace the retained native amd64 reference host
or authorized unseen holdout required by ADR-0009. No images or raw OCR are published here.

Container identities:

- Baseline: `sha256:cca26c1d17bbed0e956f52b53ce142789677ecd7da5150b90cb92b33fcef9645`
- Repaired: `sha256:d9e693c33b332cc23829f461b1b2d187a102c89e5fe9b6653b4945d96904aa24`
