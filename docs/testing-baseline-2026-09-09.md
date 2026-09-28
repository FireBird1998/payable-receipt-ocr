# Local capability baseline — 9 September 2026

The development benchmark now compares expected payable amounts and currencies with actual
recognition results. It reports incorrect strong results, no-suggestion cases, errors,
confirmation-contract violations, per-category accuracy, and latency including failed calls.

## Observed results

| Development set | Exact amount + currency | Incorrect strong results |
| --- | ---: | ---: |
| Existing local Blinkit screenshots | 10 / 10 | 0 |
| New public Blinkit screenshots | 5 / 5 | 0 |
| New public Zepto screenshots | 5 / 5 | 0 |
| New public Swiggy screenshots | 5 / 5 | 0 |
| Committed synthetic capability fixtures | 8 / 8 | 0 |

The 15 new public examples produced 9 strong and 6 review suggestions. Every result required
human confirmation. There were no OCR errors or deadline-exceeded results in that run.
The median duration was 2.41 seconds and the p95 was 4.83 seconds.

Swiggy coverage included three food-delivery bills, one Instamart bill, and one Dineout payment
confirmation. The samples include light/dark layouts, crossed-out prices, discounts, fees,
wallet credit, modal overlays, and rounded payable amounts. Labels were recorded visually
before OCR; exact image hashes were checked for duplicates.

The synthetic set covers competing amounts, wallet deductions after grand total, cash/change,
zero payable amounts, the rupee symbol, and two cases with no payable evidence. Unlike the
real-image sets, these fixtures and their labels are included in the repository.

## Improvement candidates

- Five correct public-image results raised currency-conflict warnings: four Zepto examples
  and the Swiggy Instamart example. Inspect their currency evidence before changing grading.
- Two dark-mode Blinkit examples took 4.83 and 4.76 seconds, close to the default 5-second
  deadline. Profile these cases before changing preprocessing or the pass schedule.
- One Blinkit example returned the correct amount with a competing-total warning.

No recognition-algorithm change was made for this evaluation.

## Reproducibility and limits

These are small, deliberately selected development sets, evaluated locally on macOS with
Python 3.13.12, Tesseract 5.5.3, and the pinned English/Devanagari models. They do not establish
general receipt accuracy, production performance, or the v1 release gate. The release gate
still requires its separate frozen corpus and conformant reference runtime.

Real screenshots, their labels and paths, raw results, and the local screenshot gallery are
excluded from this repository under the contribution rules. Consequently, the public repository
can reproduce the synthetic checks but cannot independently reproduce the real-image results.

Run the included checks from the repository root:

```bash
.venv/bin/python tools/benchmark.py \
  --manifest tests/fixtures/capability-cases.json \
  --repetitions 1 \
  --output output/synthetic-capabilities.json
```

See [Testing receipt OCR locally](testing.md) to build a private labelled set and compare changes.
